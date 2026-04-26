import hashlib

from django.core.cache import cache
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Product, ProductView, RenderJob
from .serializers import (
    ProductSerializer,
    ProductViewSerializer,
    RenderJobSerializer,
    RenderSubmitSerializer,
)


# ──────────────────────────────────────────────
#  Products
# ──────────────────────────────────────────────

class ProductListView(APIView):
    """GET /api/products/ — list all active products with their views."""

    def get(self, request):
        products = Product.objects.filter(is_active=True).prefetch_related("views")
        serializer = ProductSerializer(products, many=True, context={"request": request})
        return Response(serializer.data)


class ProductDetailView(APIView):
    """GET /api/products/<id>/ — single product detail."""

    def get(self, request, pk):
        product = get_object_or_404(Product, pk=pk, is_active=True)
        serializer = ProductSerializer(product, context={"request": request})
        return Response(serializer.data)


class ProductViewsListView(APIView):
    """GET /api/products/<id>/views/ — all views for a product."""

    def get(self, request, pk):
        product = get_object_or_404(Product, pk=pk, is_active=True)
        views = product.views.all()
        serializer = ProductViewSerializer(views, many=True, context={"request": request})
        return Response(serializer.data)


# ──────────────────────────────────────────────
#  Rendering
# ──────────────────────────────────────────────

class RenderSubmitView(APIView):
    """
    POST /api/render/
    Accepts a design file + product_view_id, creates a RenderJob,
    checks the cache first, then dispatches Celery task.
    """

    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = RenderSubmitSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        product_view_id = serializer.validated_data["product_view_id"]
        design_file = serializer.validated_data["design"]
        opacity = serializer.validated_data["design_opacity"]

        product_view = get_object_or_404(ProductView, pk=product_view_id)

        # Guard: analysis must be complete before rendering
        if product_view.analysis_status != "done":
            return Response(
                {
                    "error": (
                        f"Product view '{product_view.view_label}' analysis is "
                        f"'{product_view.analysis_status}'. Please wait for analysis "
                        f"to complete before rendering."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Compute design file SHA-256 for cache de-duplication
        design_bytes = design_file.read()
        design_hash = hashlib.sha256(design_bytes).hexdigest()
        design_file.seek(0)  # reset for later save

        # Check cache for an identical prior render
        cache_key = f"render:{product_view_id}:{design_hash}:{opacity}"
        cached_rel_path = cache.get(cache_key)
        if cached_rel_path:
            # Build absolute URL from the stored relative media path
            from django.conf import settings as django_settings
            abs_url = request.build_absolute_uri(
                f"{django_settings.MEDIA_URL}{cached_rel_path}"
            )
            return Response(
                {
                    "cached": True,
                    "result_image_url": abs_url,
                    "status": "done",
                },
                status=status.HTTP_200_OK,
            )

        # Create the RenderJob record
        job = RenderJob.objects.create(
            product_view=product_view,
            design_image=design_file,
            design_opacity=opacity,
            design_hash=design_hash,
            status="pending",
        )

        # Dispatch async Celery task
        from rendering.tasks import render_product_view
        render_product_view.delay(str(job.id))

        return Response(
            {
                "job_id": str(job.id),
                "status": "pending",
                "estimated_seconds": 3,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class RenderStatusView(APIView):
    """GET /api/render/<job_id>/status/ — poll job status."""

    def get(self, request, job_id):
        job = get_object_or_404(RenderJob, pk=job_id)
        serializer = RenderJobSerializer(job, context={"request": request})
        return Response(serializer.data)


class RenderResultView(APIView):
    """GET /api/render/<job_id>/result/ — return final composited image URL."""

    def get(self, request, job_id):
        job = get_object_or_404(RenderJob, pk=job_id)
        if job.status != "done":
            return Response(
                {"status": job.status, "result_image_url": None},
                status=status.HTTP_202_ACCEPTED,
            )
        serializer = RenderJobSerializer(job, context={"request": request})
        return Response(serializer.data)


class RenderAllViewsView(APIView):
    """
    POST /api/render/all/
    Submit a design to render on ALL views of a product simultaneously.
    Returns a list of job_ids.
    """

    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        product_id = request.data.get("product_id")
        design_file = request.FILES.get("design")
        opacity = float(request.data.get("design_opacity", 1.0))

        if not product_id or not design_file:
            return Response(
                {"error": "product_id and design are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        product = get_object_or_404(Product, pk=product_id, is_active=True)
        views = product.views.filter(analysis_status="done")

        if not views.exists():
            return Response(
                {"error": "No analyzed views available for this product."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        design_bytes = design_file.read()
        design_hash = hashlib.sha256(design_bytes).hexdigest()

        from rendering.tasks import render_product_view
        jobs = []
        for pv in views:
            design_file.seek(0)
            job = RenderJob.objects.create(
                product_view=pv,
                design_image=design_file,
                design_opacity=opacity,
                design_hash=design_hash,
                status="pending",
            )
            render_product_view.delay(str(job.id))
            jobs.append({"job_id": str(job.id), "view_label": pv.view_label})

        return Response(
            {"product_id": product_id, "jobs": jobs},
            status=status.HTTP_202_ACCEPTED,
        )


class ReAnalyzeView(APIView):
    """POST /api/products/views/<id>/reanalyze/ — re-trigger analysis pipeline."""

    def post(self, request, pk):
        pv = get_object_or_404(ProductView, pk=pk)
        pv.analysis_status = "pending"
        pv.save(update_fields=["analysis_status"])
        from rendering.tasks import analyze_product_view
        analyze_product_view.delay(pv.pk)
        return Response({"status": "analysis triggered", "product_view_id": pk})
