"""
rendering/tasks.py
──────────────────
Celery tasks:
  - analyze_product_view : runs the image analysis pipeline on a ProductView
  - render_product_view  : renders a design onto a ProductView (RenderJob)
"""

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

RENDERING_CFG = getattr(settings, "RENDERING", {})
CACHE_TTL = RENDERING_CFG.get("CACHE_TTL", 3600)


# ──────────────────────────────────────────────
# Task 1 — Image Analysis
# ──────────────────────────────────────────────

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    name="rendering.tasks.analyze_product_view",
)
def analyze_product_view(self, product_view_pk: int):
    """
    Runs the full analysis pipeline for a ProductView:
      - Detects surface angle
      - Computes perspective homography
      - Generates displacement map
    """
    from products.models import ProductView
    from rendering import analysis

    try:
        pv = ProductView.objects.get(pk=product_view_pk)
    except ProductView.DoesNotExist:
        logger.error("ProductView %s not found", product_view_pk)
        return

    # Mark as running
    pv.analysis_status = "running"
    pv.save(update_fields=["analysis_status"])

    try:
        results = analysis.analyze_view(pv)

        pv.surface_angle_deg = results["surface_angle_deg"]
        pv.perspective_matrix = results["perspective_matrix"]

        # Attach displacement map file path (relative to MEDIA_ROOT)
        disp_rel_path = results["displacement_map_path"]
        pv.displacement_map.name = disp_rel_path

        pv.analysis_status = "done"
        pv.save(update_fields=[
            "surface_angle_deg",
            "perspective_matrix",
            "displacement_map",
            "analysis_status",
        ])
        logger.info("Analysis complete for ProductView %s", product_view_pk)

    except Exception as exc:
        logger.exception("Analysis failed for ProductView %s: %s", product_view_pk, exc)
        pv.analysis_status = "failed"
        pv.save(update_fields=["analysis_status"])
        raise self.retry(exc=exc)


# ──────────────────────────────────────────────
# Task 2 — Render Design onto Product View
# ──────────────────────────────────────────────

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=5,
    name="rendering.tasks.render_product_view",
)
def render_product_view(self, job_id: str):
    """
    Renders a user's design onto a ProductView and saves the result.
    Checks Redis cache first; if cache hit, returns immediately.
    """
    from products.models import RenderJob
    from rendering import compositor

    try:
        job = RenderJob.objects.select_related("product_view").get(pk=job_id)
    except RenderJob.DoesNotExist:
        logger.error("RenderJob %s not found", job_id)
        return

    job.status = "processing"
    job.save(update_fields=["status"])

    try:
        pv = job.product_view

        # Check if analysis is done
        if pv.analysis_status != "done":
            raise RuntimeError(
                f"ProductView {pv.pk} analysis status is '{pv.analysis_status}', not 'done'. "
                "Cannot render until analysis is complete."
            )

        design_path = job.design_image.path

        # Build unique output path
        output_filename = f"result_{job.pk}_{uuid.uuid4().hex[:8]}.jpg"
        output_rel = Path("renders") / "results" / output_filename
        output_abs = Path(settings.MEDIA_ROOT) / output_rel

        # Run the full rendering pipeline
        compositor.render(
            product_view=pv,
            design_path=design_path,
            output_path=str(output_abs),
            opacity=job.design_opacity,
        )

        # Save result back to job
        job.result_image.name = str(output_rel)
        job.status = "done"
        job.completed_at = datetime.now(tz=timezone.utc)
        job.save(update_fields=["result_image", "status", "completed_at"])

        # Cache the result URL keyed by (product_view, design_hash, opacity)
        cache_key = f"render:{pv.pk}:{job.design_hash}:{job.design_opacity}"
        cache.set(cache_key, str(output_rel), timeout=CACHE_TTL)

        logger.info("RenderJob %s completed successfully", job_id)

    except Exception as exc:
        logger.exception("RenderJob %s failed: %s", job_id, exc)
        job.status = "failed"
        job.error_message = str(exc)
        job.completed_at = datetime.now(tz=timezone.utc)
        job.save(update_fields=["status", "error_message", "completed_at"])
        raise self.retry(exc=exc)
