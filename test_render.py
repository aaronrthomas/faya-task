import os, sys, django

os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
sys.path.insert(0, r'E:\OG\web task')
django.setup()

from products.models import ProductView, RenderJob
from rendering.tasks import render_product_view
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
import io

# Create a red test image
img = Image.new('RGBA', (300, 300), (255, 50, 50, 255))
from PIL import ImageDraw
draw = ImageDraw.Draw(img)
draw.text((80, 130), "TEST", fill=(255,255,255))
buf = io.BytesIO()
img.save(buf, 'PNG')
buf.seek(0)

# Get first analyzed view
pv = ProductView.objects.filter(analysis_status='done').first()
print(f'Using ProductView: {pv.pk} - {pv.product.name} / {pv.view_label}')

# Create a RenderJob
import hashlib
design_bytes = buf.getvalue()
design_hash = hashlib.sha256(design_bytes).hexdigest()[:16]

design_file = SimpleUploadedFile('test_design.png', design_bytes, content_type='image/png')
job = RenderJob.objects.create(
    product_view=pv,
    design_image=design_file,
    design_opacity=1.0,
    design_hash=design_hash,
    status='pending',
)
print(f'Created job: {job.id}')

# Run the task synchronously
render_product_view(str(job.id))

# Check result
job.refresh_from_db()
print(f'Job status: {job.status}')
print(f'Result image: {job.result_image.name if job.result_image else "NONE"}')
print(f'Error: {job.error_message}')
