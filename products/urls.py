from django.urls import path
from . import views

urlpatterns = [
    # Products
    path("products/", views.ProductListView.as_view(), name="product-list"),
    path("products/<int:pk>/", views.ProductDetailView.as_view(), name="product-detail"),
    path("products/<int:pk>/views/", views.ProductViewsListView.as_view(), name="product-views"),
    path("products/views/<int:pk>/reanalyze/", views.ReAnalyzeView.as_view(), name="reanalyze"),

    # Rendering
    path("render/", views.RenderSubmitView.as_view(), name="render-submit"),
    path("render/all/", views.RenderAllViewsView.as_view(), name="render-all"),
    path("render/<uuid:job_id>/status/", views.RenderStatusView.as_view(), name="render-status"),
    path("render/<uuid:job_id>/result/", views.RenderResultView.as_view(), name="render-result"),
]
