from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse

from .models import Product, ProductView, RenderJob


class ProductViewInline(admin.TabularInline):
    model = ProductView
    extra = 1
    fields = (
        "view_label",
        "base_image",
        "print_area_x",
        "print_area_y",
        "print_area_w",
        "print_area_h",
        "analysis_status",
        "sort_order",
    )
    readonly_fields = ("analysis_status",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "is_active", "view_count", "created_at")
    list_filter = ("category", "is_active")
    search_fields = ("name", "description")
    inlines = [ProductViewInline]

    def view_count(self, obj):
        return obj.views.count()
    view_count.short_description = "Views"


@admin.register(ProductView)
class ProductViewAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "view_label",
        "analysis_status",
        "surface_angle_deg",
        "base_image_thumbnail",
        "displacement_map_thumbnail",
        "reanalyze_action_link",
    )
    list_filter = ("analysis_status", "view_label", "product__category")
    search_fields = ("product__name",)
    readonly_fields = (
        "analysis_status",
        "surface_angle_deg",
        "perspective_matrix",
        "displacement_map",
        "base_image_thumbnail",
        "displacement_map_thumbnail",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        (
            "Product & View",
            {
                "fields": ("product", "view_label", "sort_order", "base_image", "base_image_thumbnail"),
            },
        ),
        (
            "Print Area (set manually)",
            {
                "fields": ("print_area_x", "print_area_y", "print_area_w", "print_area_h"),
                "description": "Pixel coordinates of the printable region within the base image.",
            },
        ),
        (
            "Analysis Results (auto-populated)",
            {
                "fields": (
                    "analysis_status",
                    "surface_angle_deg",
                    "perspective_matrix",
                    "displacement_map",
                    "displacement_map_thumbnail",
                ),
                "classes": ("collapse",),
            },
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )
    actions = ["trigger_reanalysis"]

    def base_image_thumbnail(self, obj):
        if obj.base_image:
            return format_html(
                '<img src="{}" style="max-height:120px;border-radius:6px;" />',
                obj.base_image.url,
            )
        return "—"
    base_image_thumbnail.short_description = "Preview"

    def displacement_map_thumbnail(self, obj):
        if obj.displacement_map:
            return format_html(
                '<img src="{}" style="max-height:80px;border-radius:4px;filter:contrast(1.5);" />',
                obj.displacement_map.url,
            )
        return "—"
    displacement_map_thumbnail.short_description = "Disp Map"

    def reanalyze_action_link(self, obj):
        url = reverse("reanalyze", kwargs={"pk": obj.pk})
        return format_html('<a href="{}?next=." class="button">Re-analyze</a>', url)
    reanalyze_action_link.short_description = "Actions"

    @admin.action(description="Re-run analysis pipeline on selected views")
    def trigger_reanalysis(self, request, queryset):
        from rendering.tasks import analyze_product_view
        count = 0
        for pv in queryset:
            pv.analysis_status = "pending"
            pv.save(update_fields=["analysis_status"])
            analyze_product_view.delay(pv.pk)
            count += 1
        self.message_user(request, f"Analysis triggered for {count} product view(s).")


@admin.register(RenderJob)
class RenderJobAdmin(admin.ModelAdmin):
    list_display = ("id", "product_view", "status", "created_at", "completed_at", "result_thumbnail")
    list_filter = ("status", "product_view__product__category")
    readonly_fields = (
        "id",
        "product_view",
        "design_image",
        "result_image",
        "status",
        "error_message",
        "design_hash",
        "created_at",
        "completed_at",
        "result_thumbnail",
    )

    def result_thumbnail(self, obj):
        if obj.result_image:
            return format_html(
                '<img src="{}" style="max-height:80px;border-radius:4px;" />',
                obj.result_image.url,
            )
        return "—"
    result_thumbnail.short_description = "Result"
