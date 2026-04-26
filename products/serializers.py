from rest_framework import serializers
from .models import Product, ProductView, RenderJob


class ProductViewSerializer(serializers.ModelSerializer):
    base_image_url = serializers.SerializerMethodField()
    displacement_map_url = serializers.SerializerMethodField()
    print_area_rect = serializers.SerializerMethodField()

    class Meta:
        model = ProductView
        fields = [
            "id",
            "view_label",
            "base_image_url",
            "displacement_map_url",
            "print_area_x",
            "print_area_y",
            "print_area_w",
            "print_area_h",
            "print_area_rect",
            "surface_angle_deg",
            "analysis_status",
            "sort_order",
        ]

    def get_base_image_url(self, obj):
        request = self.context.get("request")
        if obj.base_image and request:
            return request.build_absolute_uri(obj.base_image.url)
        return None

    def get_displacement_map_url(self, obj):
        request = self.context.get("request")
        if obj.displacement_map and request:
            return request.build_absolute_uri(obj.displacement_map.url)
        return None

    def get_print_area_rect(self, obj):
        return {
            "x": obj.print_area_x,
            "y": obj.print_area_y,
            "w": obj.print_area_w,
            "h": obj.print_area_h,
        }


class ProductSerializer(serializers.ModelSerializer):
    views = ProductViewSerializer(many=True, read_only=True)
    category_display = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "description",
            "category",
            "category_display",
            "is_active",
            "views",
            "created_at",
        ]


class RenderJobSerializer(serializers.ModelSerializer):
    result_image_url = serializers.SerializerMethodField()
    product_view_detail = ProductViewSerializer(source="product_view", read_only=True)

    class Meta:
        model = RenderJob
        fields = [
            "id",
            "product_view",
            "product_view_detail",
            "design_opacity",
            "status",
            "error_message",
            "result_image_url",
            "created_at",
            "completed_at",
        ]
        read_only_fields = ["id", "status", "result_image_url", "created_at", "completed_at"]

    def get_result_image_url(self, obj):
        request = self.context.get("request")
        if obj.result_image and request:
            return request.build_absolute_uri(obj.result_image.url)
        return None


class RenderSubmitSerializer(serializers.Serializer):
    """Serializer for the render submission endpoint (POST /api/render/)."""

    product_view_id = serializers.IntegerField()
    design = serializers.ImageField()
    design_opacity = serializers.FloatField(default=1.0, min_value=0.1, max_value=1.0)
