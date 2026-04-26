import uuid
from django.db import models


class Product(models.Model):
    """A product (e.g. T-Shirt, Hoodie, Cap) with multiple view angles."""

    CATEGORY_CHOICES = [
        ("tshirt", "T-Shirt"),
        ("hoodie", "Hoodie"),
        ("cap", "Cap"),
        ("mug", "Mug"),
        ("tote", "Tote Bag"),
        ("other", "Other"),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default="tshirt")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"


class ProductView(models.Model):
    """
    One angle/view of a product (front, back, side, etc.).
    Holds the base image, print-area coordinates, and auto-computed
    analysis results (perspective matrix, displacement map).
    """

    VIEW_CHOICES = [
        ("front", "Front"),
        ("back", "Back"),
        ("left", "Left Side"),
        ("right", "Right Side"),
        ("detail", "Detail"),
    ]

    ANALYSIS_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("done", "Done"),
        ("failed", "Failed"),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="views")
    view_label = models.CharField(max_length=20, choices=VIEW_CHOICES, default="front")
    base_image = models.ImageField(upload_to="products/base/")
    sort_order = models.PositiveSmallIntegerField(default=0)

    # --- Print Area (set by admin, in pixels relative to base_image) ---
    print_area_x = models.PositiveIntegerField(default=0, help_text="Left edge of print area (px)")
    print_area_y = models.PositiveIntegerField(default=0, help_text="Top edge of print area (px)")
    print_area_w = models.PositiveIntegerField(default=300, help_text="Width of print area (px)")
    print_area_h = models.PositiveIntegerField(default=300, help_text="Height of print area (px)")

    # --- Auto-computed by analysis pipeline ---
    analysis_status = models.CharField(max_length=20, choices=ANALYSIS_STATUS_CHOICES, default="pending")
    displacement_map = models.ImageField(upload_to="products/disp_maps/", blank=True, null=True)
    surface_angle_deg = models.FloatField(default=0.0, help_text="Detected surface tilt angle (degrees)")
    perspective_matrix = models.JSONField(default=list, blank=True, help_text="3x3 homography matrix as nested list")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["product", "sort_order", "view_label"]
        unique_together = [("product", "view_label")]

    def __str__(self):
        return f"{self.product.name} — {self.get_view_label_display()}"

    @property
    def print_area_rect(self):
        """Return print area as (x, y, w, h) tuple."""
        return (self.print_area_x, self.print_area_y, self.print_area_w, self.print_area_h)


class RenderJob(models.Model):
    """
    Tracks a single render request: a user's design applied to a ProductView.
    Processed asynchronously via Celery.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("done", "Done"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product_view = models.ForeignKey(ProductView, on_delete=models.CASCADE, related_name="render_jobs")
    design_image = models.ImageField(upload_to="uploads/designs/")
    result_image = models.ImageField(upload_to="renders/results/", blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    error_message = models.TextField(blank=True)

    # Design color / blend options
    design_opacity = models.FloatField(default=1.0, help_text="0.0–1.0 opacity of the design layer")

    # SHA-256 hash of design file used for result caching
    design_hash = models.CharField(max_length=64, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"RenderJob {self.id} — {self.product_view} [{self.status}]"
