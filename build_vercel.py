#!/usr/bin/env python
"""
build_vercel.py
───────────────
Vercel build script — runs during deployment.
  1. Collects static files
  2. Copies db.sqlite3 to /tmp so the serverless function can use it
  3. Runs migrations
"""
import os
import shutil
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def run(cmd):
    print(f">>> {cmd}")
    subprocess.check_call(cmd, shell=True, cwd=BASE_DIR)


def main():
    # 1. Collect static files
    run(f"{sys.executable} manage.py collectstatic --noinput")

    # 2. Copy the dev database to /tmp so cold starts have data
    src_db = os.path.join(BASE_DIR, "db.sqlite3")
    dst_db = "/tmp/db.sqlite3"
    if os.path.exists(src_db):
        shutil.copy2(src_db, dst_db)
        print(f"Copied {src_db} → {dst_db}")

    # 3. Ensure /tmp/media exists (for uploads and renders)
    os.makedirs("/tmp/media", exist_ok=True)

    # 4. Run migrations on the /tmp database
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    run(f"{sys.executable} manage.py migrate --noinput")

    print("Build complete!")


if __name__ == "__main__":
    main()
