from django.urls import path
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie


@ensure_csrf_cookie
def customizer_view(request):
    return render(request, "customizer.html")


urlpatterns = [
    path("", customizer_view, name="customizer"),
]
