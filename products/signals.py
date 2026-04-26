"""
Django signals for the products app.
Triggers the analysis pipeline automatically when a ProductView base image is saved.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender="products.ProductView")
def trigger_analysis_on_image_save(sender, instance, created, **kwargs):
    """
    When a ProductView is saved with a base_image, kick off the analysis pipeline.
    Uses a deferred import to avoid circular imports at startup.
    """
    if not instance.base_image:
        return

    # Only re-analyze if analysis is not already done or running
    if instance.analysis_status in ("done", "running"):
        return

    # Import here to avoid circular import at module load time
    try:
        from rendering.tasks import analyze_product_view
        analyze_product_view.delay(instance.pk)
    except Exception:
        # Redis may not be running (e.g. during seeding / tests) — skip gracefully.
        # Analysis can be triggered manually via Admin or the /api/reanalyze/ endpoint.
        pass
