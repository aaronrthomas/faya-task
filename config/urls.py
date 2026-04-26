from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from django.views.static import serve

urlpatterns = [
    path("", lambda request: redirect("customizer/"), name="home"),
    path("admin/", admin.site.urls),
    path("api/", include("products.urls")),
    path("customizer/", include("products.frontend_urls")),
    # Serve media files in both dev and production
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
