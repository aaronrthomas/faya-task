import os
import shutil
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# ── Vercel cold-start initialization ──
# /tmp is wiped between invocations — copy bundled DB and ensure media dir exists
if os.getenv("VERCEL"):
    _base = Path(__file__).resolve().parent.parent
    _src_db = _base / "db.sqlite3"
    _dst_db = Path("/tmp/db.sqlite3")
    if _src_db.is_file() and not _dst_db.is_file():
        shutil.copy2(str(_src_db), str(_dst_db))
    Path("/tmp/media").mkdir(parents=True, exist_ok=True)

import django
from django.core.wsgi import get_wsgi_application

# Run migrations on first cold start (creates tables in /tmp/db.sqlite3)
application = get_wsgi_application()

# Vercel expects the WSGI app as `app`
app = application
