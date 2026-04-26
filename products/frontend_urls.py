from django.urls import path
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.conf import settings


@ensure_csrf_cookie
def customizer_view(request):
    return render(request, "customizer.html", {
        "api_base_url": settings.API_BASE_URL,
    })


urlpatterns = [
    path("", customizer_view, name="customizer"),
]
