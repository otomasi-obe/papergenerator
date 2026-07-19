"""Standalone image generation worker runner.

Run outside gunicorn/gevent:
  python -m tools.image_generation.worker_runner
"""
import signal
import time
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env from backend root (override=True so .env is source of truth)
# worker_runner.py is at backend/tools/image_generation/ → backend root is parents[2]
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)

# Ensure we can import from backend root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Create Flask app with minimal config (same as main.py)
from flask import Flask
from utils.database import db

app = Flask(__name__)

# Database config (copied from main.py - uses root .env DATABASE_URL)
_db_url = os.getenv("DATABASE_URL")
if not _db_url:
    raise RuntimeError("DATABASE_URL environment variable is required. Set it in .env")
app.config["SQLALCHEMY_DATABASE_URI"] = _db_url

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# JWT config (minimal for worker)
_jwt_secret = os.getenv("JWT_SECRET_KEY")
if not _jwt_secret:
    _jwt_secret = os.getenv("SECRET_KEY")
if not _jwt_secret:
    import secrets
    _jwt_secret = secrets.token_hex(32)
app.config["JWT_SECRET_KEY"] = _jwt_secret

# Secret key
_secret_key = os.getenv("SECRET_KEY") or _jwt_secret
app.config["SECRET_KEY"] = _secret_key

db.init_app(app)

from tools.image_generation.worker import start_image_workers

_stop = False


def _handle_stop(signum, frame):  # noqa: ARG001
    global _stop
    _stop = True


def main() -> int:
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    # Verify key loaded
    api_key = os.getenv("IMAGE_GEN_API_KEY")
    if api_key:
        print(f"Loaded IMAGE_GEN_API_KEY: {api_key[:20]}...")
    else:
        print("WARNING: IMAGE_GEN_API_KEY not loaded from .env")

    # Verify IMAGE_GEN_API_URL
    api_url = os.getenv("IMAGE_GEN_API_URL")
    if api_url:
        print(f"Loaded IMAGE_GEN_API_URL: {api_url}")
    else:
        print("IMAGE_GEN_API_URL not set, using default https://ai.otomasi.app")

    with app.app_context():
        db.create_all()
        start_image_workers(app)
        print("paper image worker started", flush=True)
        while not _stop:
            time.sleep(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())