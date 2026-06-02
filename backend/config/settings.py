"""
Application Configuration
=========================
Centralized configuration for Flask app, database, JWT, and other settings.
"""

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv


def load_environment():
    """Load environment variables from .env files.

    IMPORTANT: tests set DATABASE_URL to sqlite:///:memory: BEFORE importing
    app.py (see backend/tests/conftest.py). If we blindly call load_dotenv with
    override=True the production Postgres URL from .env clobbers the test value
    and the test fixture's db.drop_all() then runs against the live database.
    That happened once. Never again — when we detect a sqlite test override
    already in place we DON'T override env from .env.
    """
    _in_tests = (
        os.environ.get("PYTEST_CURRENT_TEST") is not None
        or os.environ.get("FLASK_ENV") == "testing"
        or (os.environ.get("DATABASE_URL", "").startswith("sqlite:"))
    )
    backend_dir = Path(__file__).parent.parent
    load_dotenv(backend_dir.parent / ".env", override=not _in_tests)
    load_dotenv(backend_dir / ".env", override=not _in_tests)
    return _in_tests


def configure_app(app):
    """Configure Flask app with all necessary settings."""
    _in_tests = load_environment()

    # Database configuration
    _db_url = os.getenv("DATABASE_URL")
    if not _db_url:
        raise RuntimeError("DATABASE_URL environment variable is required. Set it in .env")
    app.config["SQLALCHEMY_DATABASE_URI"] = _db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Pooling options only make sense for server-grade DBs (Postgres/MySQL).
    # Under sqlite (used by tests) SQLAlchemy uses StaticPool which rejects
    # pool_size/max_overflow/pool_timeout. Skip those keys when on sqlite.
    if not _db_url.startswith("sqlite:"):
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "pool_size": 12,
            "max_overflow": 28,
            "pool_timeout": 30,
            "pool_recycle": 1800,
            "pool_pre_ping": True,
        }
    else:
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "pool_pre_ping": True,
        }

    # JWT configuration
    _jwt_secret = os.getenv("JWT_SECRET_KEY")
    if not _jwt_secret or _jwt_secret == "change-me-in-production":
        raise RuntimeError("JWT_SECRET_KEY must be set to a secure value in .env")
    app.config["JWT_SECRET_KEY"] = _jwt_secret

    # JWT in httpOnly cookies (XSS-safe) + CSRF double-submit protection.
    # Bearer header still accepted as a fallback so signed-URL/E2E tooling and
    # legacy clients keep working during rollout.
    app.config["JWT_TOKEN_LOCATION"] = ["cookies", "headers"]
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1)
    app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=7)
    app.config["JWT_COOKIE_SECURE"] = os.getenv("JWT_COOKIE_SECURE", "true").lower() == "true"
    app.config["JWT_COOKIE_HTTPONLY"] = True
    app.config["JWT_COOKIE_SAMESITE"] = "Lax"  # Lax keeps SSO callback redirects working
    app.config["JWT_COOKIE_CSRF_PROTECT"] = True
    app.config["JWT_ACCESS_CSRF_HEADER_NAME"] = "X-CSRF-TOKEN"
    app.config["JWT_REFRESH_CSRF_HEADER_NAME"] = "X-CSRF-TOKEN"
    app.config["JWT_ACCESS_COOKIE_PATH"] = "/api/"
    app.config["JWT_REFRESH_COOKIE_PATH"] = "/api/auth/refresh"

    # Secret key configuration
    _secret_key = os.getenv("SECRET_KEY")
    if not _secret_key or _secret_key in ("flask-secret-key", "change-me-in-production"):
        raise RuntimeError("SECRET_KEY must be set to a secure non-default value in .env")
    app.config["SECRET_KEY"] = _secret_key

    # Session cookie hardening — flask sessions are only used for OAuth state, but
    # defaults are unsafe behind a reverse proxy.
    app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "true").lower() == "true"
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"  # Lax (not Strict) so OAuth callback works

    # Server-signed URL secret — used for generating short-lived signed image/file
    # URLs that don't expose the bearer JWT in query strings or referer headers.
    # Falls back to SECRET_KEY so existing deployments don't break, but it's
    # recommended to set a dedicated rotating value.
    app.config["SIGNED_URL_SECRET"] = os.getenv("SIGNED_URL_SECRET") or _secret_key

    # Per-request body cap. Each PaperFile is capped at 10 MB by files_bp itself,
    # but multipart uploads bundle all selected files in one POST so 4 PDFs of
    # ~9 MB each used to 413 the request. Bumped to 60 MB so up to 5 large PDFs
    # can ride the same multipart payload (form overhead included).
    app.config["MAX_CONTENT_LENGTH"] = 60 * 1024 * 1024  # 60MB max upload

    return _in_tests


# Application paths
BACKEND_DIR = Path(__file__).parent.parent
UPLOAD_FOLDER = BACKEND_DIR / "data/uploads"
EXPORT_FOLDER = BACKEND_DIR / "data" / "exports"
TEMPLATE_FOLDER = BACKEND_DIR / "template"
LOG_FILE = BACKEND_DIR / "data" / "logs" / "app.log"

# Ensure directories exist
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
EXPORT_FOLDER.mkdir(parents=True, exist_ok=True)

# AI Model configuration
AIOTOMASI_MODEL = os.getenv("MODELGENERATE") or "VIOLA-GENERATE"

# Upload limits
MAX_PDF_FILES = 10
MAX_WORDS_PER_FILE = 5000

# Job timeout configuration
AIJOB_PENDING_TIMEOUT_SECONDS = 15 * 60  # 15 minutes
