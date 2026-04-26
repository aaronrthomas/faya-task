from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from django.views.static import serve
from django.http import JsonResponse


def api_404(request, exception=None):
    """Return JSON 404 for /api/ requests, default HTML for everything else."""
    if request.path.startswith("/api/"):
        return JsonResponse({"error": "Not found."}, status=404)
    # Fall through to Django's normal HTML 404
    from django.views.defaults import page_not_found
    return page_not_found(request, exception)


def api_500(request):
    """Return JSON 500 for /api/ requests, default HTML for everything else."""
    if request.path.startswith("/api/"):
        return JsonResponse({"error": "Internal server error."}, status=500)
    from django.views.defaults import server_error
    return server_error(request)


urlpatterns = [
    path("", lambda request: redirect("customizer/"), name="home"),
    path("admin/", admin.site.urls),
    path("api/", include("products.urls")),
    path("customizer/", include("products.frontend_urls")),
    # Serve media files in both dev and production
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

handler404 = "config.urls.api_404"
handler500 = "config.urls.api_500"
