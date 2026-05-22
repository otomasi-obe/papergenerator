"""Pytest config — isolate from system pytest plugins (e.g. ROS launch_testing).

Also CRITICAL: force test DB env vars BEFORE any test or app module imports.
Without this, .env is loaded at app-import time and tests would happily
``db.drop_all()`` against the production Postgres database (this happened
once — never again). We use plain assignment, not ``setdefault``, so any
inherited value (from .env, shell, or pm2) is overridden.
"""
import os

os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

# Force in-memory test DB regardless of any inherited DATABASE_URL.
# Tests that need a real DB must be opt-in (e.g. an integration marker).
_db = os.environ.get("DATABASE_URL", "")
if not _db.startswith("sqlite:"):
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"

# Required-by-app secrets — give safe test defaults so app.py import doesn't
# RuntimeError when the host .env hasn't been loaded yet.
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-not-for-production")
os.environ.setdefault("SECRET_KEY", "test-flask-secret-not-for-production")
os.environ.setdefault("FLASK_ENV", "testing")

# Belt-and-suspenders: refuse to run against any host that looks like a real DB.
_url = os.environ["DATABASE_URL"]
if not _url.startswith("sqlite:"):
    raise RuntimeError(
        f"Test suite refuses to run against non-sqlite DATABASE_URL: {_url!r}"
    )
