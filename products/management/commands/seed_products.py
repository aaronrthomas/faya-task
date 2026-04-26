"""
Management command: python manage.py seed_products
Creates sample Product entries with placeholder ProductViews for testing.
"""
import urllib.request
from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from products.models import Product, ProductView


SAMPLE_PRODUCTS = [
    {
        "name": "Classic Unisex T-Shirt",
        "category": "tshirt",
        "description": "100% cotton premium tee, ideal for custom prints.",
        "views": [
            {
                "view_label": "front",
                "sort_order": 0,
                "print_area_x": 160,
                "print_area_y": 140,
                "print_area_w": 280,
                "print_area_h": 280,
            },
            {
                "view_label": "back",
                "sort_order": 1,
                "print_area_x": 150,
                "print_area_y": 130,
                "print_area_w": 300,
                "print_area_h": 300,
            },
        ],
    },
    {
        "name": "Pullover Hoodie",
        "category": "hoodie",
        "description": "Heavyweight fleece hoodie with kangaroo pocket.",
        "views": [
            {
                "view_label": "front",
                "sort_order": 0,
                "print_area_x": 155,
                "print_area_y": 145,
                "print_area_w": 260,
                "print_area_h": 260,
            },
        ],
    },
    {
        "name": "Snapback Cap",
        "category": "cap",
        "description": "Structured six-panel cap with flat brim.",
        "views": [
            {
                "view_label": "front",
                "sort_order": 0,
                "print_area_x": 75,
                "print_area_y": 40,
                "print_area_w": 180,
                "print_area_h": 110,
            },
        ],
    },
    {
        "name": "Canvas Tote Bag",
        "category": "tote",
        "description": "Eco-friendly natural canvas tote with long handles.",
        "views": [
            {
                "view_label": "front",
                "sort_order": 0,
                "print_area_x": 80,
                "print_area_y": 100,
                "print_area_w": 240,
                "print_area_h": 240,
            },
        ],
    },
]


def _create_placeholder_image(label: str, W: int = 600, H: int = 700) -> bytes:
    """Generate a simple solid-colour PNG placeholder using PIL."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        import io

        colors = {
            "tshirt": (220, 220, 225),
            "hoodie": (180, 180, 190),
            "cap": (210, 205, 195),
            "tote": (230, 220, 200),
        }
        bg = colors.get(label.split("-")[0], (210, 210, 210))
        img = Image.new("RGB", (W, H), color=bg)
        draw = ImageDraw.Draw(img)

        # Draw a subtle neckline for tshirt/hoodie
        if "tshirt" in label or "hoodie" in label:
            # Body outline
            draw.rectangle([80, 100, W - 80, H - 60], outline=(150, 150, 155), width=3)
            # Collar
            draw.ellipse([W // 2 - 60, 80, W // 2 + 60, 180], outline=(150, 150, 155), width=3)
            # Sleeves
            draw.polygon([(80, 100), (10, 250), (80, 300)], outline=(150, 150, 155), width=3)
            draw.polygon([(W - 80, 100), (W - 10, 250), (W - 80, 300)], outline=(150, 150, 155), width=3)

        # Label
        draw.text((W // 2 - 60, H // 2 - 20), label.upper(), fill=(130, 130, 130))

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        # Minimal fallback — 1×1 white PNG
        return (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
            b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
            b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )


class Command(BaseCommand):
    help = "Seed the database with sample products and product views for testing."

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Seeding sample products…"))

        for product_data in SAMPLE_PRODUCTS:
            product, created = Product.objects.get_or_create(
                name=product_data["name"],
                defaults={
                    "category": product_data["category"],
                    "description": product_data["description"],
                    "is_active": True,
                },
            )
            action = "Created" if created else "Found"
            self.stdout.write(f"  {action}: {product.name}")

            for view_data in product_data["views"]:
                pv, pv_created = ProductView.objects.get_or_create(
                    product=product,
                    view_label=view_data["view_label"],
                    defaults={
                        "print_area_x": view_data["print_area_x"],
                        "print_area_y": view_data["print_area_y"],
                        "print_area_w": view_data["print_area_w"],
                        "print_area_h": view_data["print_area_h"],
                        "sort_order": view_data["sort_order"],
                    },
                )

                if pv_created or not pv.base_image:
                    label = f"{product_data['category']}-{view_data['view_label']}"
                    img_bytes = _create_placeholder_image(label)
                    pv.base_image.save(
                        f"{label}_base.png",
                        ContentFile(img_bytes),
                        save=True,
                    )
                    self.stdout.write(f"    + View '{view_data['view_label']}' created with placeholder image")
                else:
                    self.stdout.write(f"    · View '{view_data['view_label']}' already exists")

        self.stdout.write(self.style.SUCCESS("Done! Seeding complete."))
        self.stdout.write(
            "  NOTE: Upload real product images via Admin -> Product Views "
            "to get proper rendering results."
        )
