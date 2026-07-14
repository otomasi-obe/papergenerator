"""
PaperFull - Backend API Server
=====================================
Flask API for AI-powered academic paper generation and DOCX export.
Supports IEEE conference paper format, Google OAuth login, PostgreSQL storage.
"""

import importlib
import json
import logging
import os
import re
import sys
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Add backend/ to sys.path so tools.*, utils.* are importable
_BACKEND_DIR = str(Path(__file__).resolve().parent)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
# Add repo root (parent of backend/) to sys.path so the top-level
# SLR modules are now in tools.Literatur/
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from dotenv import load_dotenv
from flask import Flask, Response, g, jsonify, request, send_file
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    create_refresh_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
    set_access_cookies,
    set_refresh_cookies,
    verify_jwt_in_request,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from tools.admin import admin
from utils.auth_bp import auth, init_oauth
from tools.data.chart_api import chart_api
from tools.data.data_jobs import data_jobs
from tools.chat import simple_chat
from tools.chat.drafts import drafts_bp
from tools.File import files, _EXTRACT_POOL
from utils.health import health
from tools.image_generation.image_jobs import image_jobs
from tools.image_generation.images import paper_images, image_serve
from tools.paperfull.jobs import jobs
from tools.editor.papers import papers
from utils.quota import quota
# SLR / Literature blueprints (consolidated in slr.py)
from tools.Literatur.slr import slr_api
from utils.ai_tools.tools_api import tools_api
from utils.logging import logging_api
from utils.state_bp.state import state_bp
from utils.database.models import AiJob, Paper, db, safe_commit
from utils.job_core import (
    init_job_core as _init_job_core,
    _job_create,
    _job_get,
    _job_set_done,
    _job_set_error,
    _get_current_user_id,
    _log_api_usage,
)
from tools.payment.doku import doku_bp

# ── Sentry / GlitchTip integration (no-op when DSN empty) ────────────────────
try:
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

    _dsn = os.getenv("GLITCHTIP_DSN", "").strip()
    if _dsn:
        sentry_sdk.init(
            dsn=_dsn,
            integrations=[FlaskIntegration(), SqlalchemyIntegration()],
            traces_sample_rate=0.05,
            send_default_pii=False,
            release=os.getenv("SENTRY_RELEASE", "dev"),
            environment=os.getenv("FLASK_ENV", "production"),
        )
except Exception as e:
    logging.getLogger(__name__).warning(f"Failed to initialize Sentry: {e}")
from tools.editor.chunked import GenerationCancelled
from tools.editor.single import generate_paper_json_single
from utils.ai_tools.model_config import get_primary_generate_model

# Load environment variables.
#
# IMPORTANT: tests set DATABASE_URL to ``sqlite:///:memory:`` BEFORE importing
# app.py (see backend/tests/conftest.py). If we blindly call load_dotenv with
# override=True the production Postgres URL from .env clobbers the test value
# and the test fixture's ``db.drop_all()`` then runs against the live database.
# That happened once. Never again — when we detect a sqlite test override
# already in place we DON'T override env from .env.
_in_tests = (
    os.environ.get("PYTEST_CURRENT_TEST") is not None
    or os.environ.get("FLASK_ENV") == "testing"
    or (os.environ.get("DATABASE_URL", "").startswith("sqlite:"))
)
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=not _in_tests)
load_dotenv(Path(__file__).resolve().parent / ".env", override=not _in_tests)

# Bridge numbered AIOTOMASI provider slots (AIOTOMASI_API1/APIKEY1) onto the
# base names (AIOTOMASI_API/AIOTOMASI_APIKEY) that every route reads. The
# canonical .env only declares numbered slots, so without this the base
# lookups return empty and generation fails with "not configured".
try:
    from utils.core.env_loader import normalize_aiotomasi_aliases
    normalize_aiotomasi_aliases()
except Exception as _e:
    logging.getLogger(__name__).warning("Failed to normalize AIOTOMASI aliases: %s", _e)

app = Flask(__name__)

# Trust nginx reverse proxy headers (X-Forwarded-For, X-Forwarded-Proto, etc.)
# This ensures url_for(..., _external=True) generates https:// URLs correctly
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# ─── Config ───────────────────────────────────────────────────────────────────
_db_url = os.getenv("DATABASE_URL")
if not _db_url:
    raise RuntimeError("DATABASE_URL environment variable is required. Set it in .env")

# ── PgBouncer integration ─────────────────────────────────────────────────
# When PGBOUNCER_ENABLED=true, rewrite the DATABASE_URL to route through
# pgbouncer on port 6543.  PgBouncer handles connection pooling at the
# transaction level so SQLAlchemy's own pool is reduced to bare minimum
# (pool_size=1, max_overflow=0).
_pg_enabled = os.getenv("PGBOUNCER_ENABLED", "false").lower() in ("true", "1", "yes")
if _pg_enabled and not _db_url.startswith("sqlite:"):
    # Parse the DSN, replace host/port with pgbouncer, drop the password
    # (pgbouncer uses trust auth on localhost).  We reconstruct the netloc
    # manually because urlparse._replace doesn't have hostname/port fields.
    from urllib.parse import urlparse, urlunparse
    _parsed = urlparse(_db_url)
    _username = _parsed.username
    _netloc = f"{_username}@localhost:6543" if _username else "localhost:6543"
    _pg_url = _parsed._replace(netloc=_netloc)
    _db_url = urlunparse(_pg_url).rstrip("?")
    logging.getLogger(__name__).info("PgBouncer enabled — routing DB through %s", _db_url)
else:
    _pg_enabled = False

app.config["SQLALCHEMY_DATABASE_URI"] = _db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# Pooling options only make sense for server-grade DBs (Postgres/MySQL).
# Under sqlite (used by tests) SQLAlchemy uses StaticPool which rejects
# pool_size/max_overflow/pool_timeout. Skip those keys when on sqlite.
if not _db_url.startswith("sqlite:"):
    if _pg_enabled:
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            # PgBouncer manages pooling — SQLAlchemy keeps 5 persistent conns
            # per worker to avoid deadlock during concurrent sweeps.
            # With 24 workers: 24×5 = 120 conns << pgbouncer default 600.
            "pool_size": 5,
            "max_overflow": 0,
            "pool_pre_ping": True,
        }
    else:
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            # PostgreSQL max_connections=300. With 24 gunicorn workers, each worker
            # gets a small pool. Total = 24×3 base + 24×4 overflow = 168 worst case.
            # Well under 300. PgBouncer recommended for production at scale
            # (transaction-level pooling) — set PGBOUNCER_ENABLED=true.
            "pool_size": 3,
            "max_overflow": 4,
            "pool_timeout": 10,       # Fail fast if pool exhausted (don't block 30s)
            "pool_recycle": 1800,     # Recycle connections every 30 min
            "pool_pre_ping": True,    # Detect stale connections before use
        }
else:
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
    }

_jwt_secret = os.getenv("JWT_SECRET_KEY")
if not _jwt_secret or _jwt_secret == "change-me-in-production":
    raise RuntimeError("JWT_SECRET_KEY must be set to a secure value in .env")
app.config["JWT_SECRET_KEY"] = _jwt_secret

# JWT in httpOnly cookies (XSS-safe) + CSRF double-submit protection.
# Bearer header still accepted as a fallback so signed-URL/E2E tooling and
# legacy clients keep working during rollout.
from datetime import timedelta as _td

app.config["JWT_TOKEN_LOCATION"] = ["cookies", "headers"]
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = _td(hours=24)
app.config["JWT_REFRESH_TOKEN_EXPIRES"] = _td(hours=24)
app.config["JWT_SESSION_COOKIE"] = False  # Persist cookies beyond browser close
app.config["JWT_COOKIE_SECURE"] = os.getenv("JWT_COOKIE_SECURE", "true").lower() == "true"
app.config["JWT_COOKIE_HTTPONLY"] = True
app.config["JWT_COOKIE_SAMESITE"] = "Lax"  # Lax keeps SSO callback redirects working
app.config["JWT_COOKIE_CSRF_PROTECT"] = True
app.config["JWT_ACCESS_CSRF_HEADER_NAME"] = "X-CSRF-TOKEN"
app.config["JWT_REFRESH_CSRF_HEADER_NAME"] = "X-CSRF-TOKEN"
app.config["JWT_ACCESS_COOKIE_PATH"] = "/api/"
app.config["JWT_REFRESH_COOKIE_PATH"] = "/api/auth/refresh"

_secret_key = os.getenv("SECRET_KEY")
if not _secret_key or _secret_key in ("flask-secret-key", "change-me-in-production"):
    raise RuntimeError("SECRET_KEY must be set to a secure non-default value in .env")
app.config["SECRET_KEY"] = _secret_key

# Session cookie hardening — flask sessions are only used for OAuth state, but
# defaults are unsafe behind a reverse proxy.
app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "true").lower() == "true"
app.config["SESSION_COOKIE_HTTPONLY"] = True
# None (with Secure) allows cross-site cookie for OAuth callback from Google
app.config["SESSION_COOKIE_SAMESITE"] = os.getenv("SESSION_COOKIE_SAMESITE", "None")
# Allow subdomains to receive the session cookie (important for OAuth callback)
_domain = os.getenv("SESSION_COOKIE_DOMAIN")
if _domain:
    app.config["SESSION_COOKIE_DOMAIN"] = _domain

# Server-signed URL secret — used for generating short-lived signed image/file
# URLs that don't expose the bearer JWT in query strings or referer headers.
# Falls back to SECRET_KEY so existing deployments don't break, but it's
# recommended to set a dedicated rotating value.
app.config["SIGNED_URL_SECRET"] = os.getenv("SIGNED_URL_SECRET") or _secret_key

# Canonical app base URL — used for generating absolute URLs in the Word
# add-in manifest. Must be set to the public-facing domain to prevent
# Host Header Injection attacks via request.host.
_APP_BASE_URL = os.getenv("APP_BASE_URL", "").rstrip("/")
if not _APP_BASE_URL:
    raise RuntimeError(
        "APP_BASE_URL must be set in .env (e.g. https://app.example.com). "
        "This is required for Word add-in manifest generation."
    )

# Per-request body cap. 100MB — prevents DoS via memory exhaustion while still
# allowing multi-file uploads of large PDFs (~10MB each × multiple files).
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100MB — prevents DoS while allowing multi-file uploads


# Friendlier 413 — Werkzeug's default returns an HTML page that the chat
# upload code treats as a generic network error. Serve JSON so the frontend
# can show "file terlalu besar" instead of "Network error".
@app.errorhandler(404)
def _on_404(_e):
    return (
        jsonify(
            {
                "error": "Endpoint tidak ditemukan",
                "code": "NOT_FOUND",
                "category": "CLIENT",
            }
        ),
        404,
    )


@app.errorhandler(413)
def _on_413(_e):
    return (
        jsonify(
            {
                "error": "Payload terlalu besar",
                "hint": (
                    f"Total upload melebihi {app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)} MB. "
                    "Coba upload file lebih sedikit atau pisah jadi beberapa kali upload."
                ),
                "code": "PAYLOAD_TOO_LARGE",
                "category": "CLIENT",
            }
        ),
        413,
    )


# BUG-25: Catch-all 500 handler for consistent error format
@app.errorhandler(500)
def _on_500(_e):
    return (
        jsonify(
            {
                "error": "Internal server error",
                "code": "INTERNAL_ERROR",
                "category": "SERVER",
            }
        ),
        500,
    )


@app.errorhandler(400)
def _on_400(_e):
    return (
        jsonify(
            {
                "error": "Bad request",
                "code": "BAD_REQUEST",
                "category": "CLIENT",
            }
        ),
        400,
    )


# ─── Extensions ───────────────────────────────────────────────────────────────
# CORS: Allow origins from env var; add dev localhost origins when not production
cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:8000,http://localhost:1000").split(",") if o.strip()]
if app.config.get("ENV") != "production" and not app.config.get("PRODUCTION"):
    cors_origins.extend(["http://localhost:8000", "http://localhost:1000", "http://localhost:5173"])
    cors_origins = list(set(cors_origins))
if not cors_origins:
    raise RuntimeError("CORS_ORIGINS must be set to at least one origin in .env")
CORS(app, supports_credentials=True, origins=cors_origins)
db.init_app(app)
jwt = JWTManager(app)

# ─── Production-safe startup checks ───────────────────────────────────────────
_flask_env = os.getenv("FLASK_ENV", "production").lower()
_is_prod = _flask_env == "production"
if _is_prod and app.debug:
    _msg = (
        "SECURITY ERROR: FLASK_DEBUG=true in production (FLASK_ENV=%s). "
        "The interactive debugger is a full RCE vector and will leak secrets. "
        "Refusing to start. Set FLASK_DEBUG=false immediately." % _flask_env
    )
    logging.getLogger(__name__).critical(_msg)
    raise RuntimeError(_msg)
elif _is_prod:
    app.debug = False

# ─── Schema migration helper (non-destructive, idempotent) ────────────────────
def _run_schema_migrations():
    """Add columns/tables that don't exist yet without ALTER-method thrashing."""
    from sqlalchemy import text, inspect
    from sqlalchemy.exc import ProgrammingError, OperationalError

    with app.app_context():
        inspector = inspect(db.engine)
        try:
            existing_cols = {c["name"] for c in inspector.get_columns("users")}
        except (ProgrammingError, OperationalError):
            # Table doesn't exist yet (fresh DB) — no migration needed
            return

        if "oauth_provider" not in existing_cols:
            log = logging.getLogger(__name__)
            log.info("Migration: adding oauth_provider column to users table")
            try:
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE users ADD COLUMN oauth_provider VARCHAR(20)"))
                    conn.commit()
                log.info("Migration: oauth_provider column added successfully")
            except (ProgrammingError, OperationalError) as e:
                log.warning("Migration: oauth_provider ALTER failed (may already exist): %s", e)

_run_schema_migrations()


# ─── JWT Error Handlers ───────────────────────────────────────────────────────
@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return jsonify({"error": "Token expired", "code": "TOKEN_EXPIRED", "category": "AUTH"}), 401


@jwt.invalid_token_loader
def invalid_token_callback(error):
    return jsonify({"error": "Invalid token", "code": "INVALID_TOKEN", "category": "AUTH"}), 401


@jwt.unauthorized_loader
def unauthorized_callback(error):
    return jsonify({"error": "Missing authorization token", "code": "UNAUTHORIZED", "category": "AUTH"}), 401


@jwt.needs_fresh_token_loader
def needs_fresh_token_callback(jwt_header, jwt_payload):
    return jsonify({"error": "Fresh token required", "code": "FRESH_TOKEN_REQUIRED", "category": "AUTH"}), 401


@jwt.revoked_token_loader
def revoked_token_callback(jwt_header, jwt_payload):
    return jsonify({"error": "Token has been revoked", "code": "TOKEN_REVOKED", "category": "AUTH"}), 401


@jwt.token_in_blocklist_loader
def _check_if_token_revoked(jwt_header, jwt_payload):
    """Check if a token's JTI has been revoked via Redis blocklist.

    Revokes both refresh (`rjti:`) and access (`ajti:`) tokens so that
    account deletion / logout-everywhere can kill active sessions immediately.
    """
    jti = jwt_payload.get("jti")
    if not jti:
        return False
    token_type = jwt_payload.get("type")
    try:
        from utils.core.redis_client import get_redis
        rc = get_redis()
        if rc:
            if token_type == "refresh":
                return rc.exists(f"rjti:{jti}") > 0
            # access tokens (and any other type) use the ajti: prefix
            return rc.exists(f"ajti:{jti}") > 0
    except Exception:
        pass
    return False


init_oauth(app)

# ─── Database query logging (debug / performance monitoring) ─────────────
# Logs every SQL query at INFO level when QUERY_LOGGING_ENABLED is true.
# In production this should only be enabled temporarily for profiling.
from sqlalchemy import event as _sa_event
from sqlalchemy.engine import Engine as _SAEngine

_QUERY_LOGGING_ENABLED = os.getenv("QUERY_LOGGING_ENABLED", "").lower() in ("1", "true", "yes")
if _QUERY_LOGGING_ENABLED:

    @_sa_event.listens_for(_SAEngine, "before_cursor_execute")
    def _before_query_log(conn, cursor, statement, parameters, context, executemany):
        query_log = logging.getLogger("database.queries")
        conn.info["query_log_start"] = time.monotonic()
        query_log.info("SQL: %s  PARAMS: %s", statement, parameters)

    @_sa_event.listens_for(_SAEngine, "after_cursor_execute")
    def _after_query_log(conn, cursor, statement, parameters, context, executemany):
        query_log = logging.getLogger("database.queries")
        elapsed = time.monotonic() - conn.info.get("query_log_start", time.monotonic())
        if elapsed > 0.5:
            query_log.warning("SLOW SQL (%.3fs): %s  PARAMS: %s", elapsed, statement, parameters)
        elif elapsed > 0.05:
            query_log.info("SQL (%.3fs): %s", elapsed, statement)

    logging.getLogger(__name__).info("database query logging enabled (QUERY_LOGGING_ENABLED=1)")


# PostgreSQL session safeguards
from sqlalchemy import event
from sqlalchemy.engine import Engine


@event.listens_for(Engine, "connect")
def _set_pg_session_defaults(dbapi_connection, _):
    """Hindari sesi nyangkut: timeout query 30 dtk, idle txn 5 menit, lock 5 dtk."""
    if not dbapi_connection.__class__.__module__.startswith("psycopg"):
        return
    try:
        with dbapi_connection.cursor() as cur:
            cur.execute("SET statement_timeout = '30s'")
            cur.execute("SET idle_in_transaction_session_timeout = '5min'")
            cur.execute("SET lock_timeout = '5s'")
        dbapi_connection.commit()
    except (AttributeError, Exception):
        logging.getLogger(__name__).exception("failed to set pg session defaults")


# Rate limiting: require Redis in production for distributed rate limiting
ratelimit_storage = os.getenv("RATELIMIT_STORAGE_URI")
if not ratelimit_storage:
    # Fall back to REDIS_URL so the limiter is SHARED across gunicorn workers.
    # memory:// is per-process — with N workers the effective limit is N× too
    # loose (16 workers here = 16× the intended cap). Flask 3.x removed the
    # "ENV" config key, so the old production guard below never fires; deriving
    # from REDIS_URL is what actually makes rate limiting correct in prod.
    _redis_url = os.getenv("REDIS_URL")
    if _redis_url:
        ratelimit_storage = _redis_url
        logging.getLogger(__name__).info(
            "Rate limiting using REDIS_URL (shared across workers)."
        )
    elif os.getenv("PRODUCTION") or os.getenv("FLASK_ENV") == "production":
        raise RuntimeError(
            "RATELIMIT_STORAGE_URI must be set in production. "
            "Use Redis: redis://localhost:***@host:port/db"
        )
    else:
        # Development/testing: allow memory storage
        ratelimit_storage = "memory://"
        logging.getLogger(__name__).warning(
            "Using memory:// for rate limiting (development only). "
            "Set RATELIMIT_STORAGE_URI=redis://... for production."
        )


def rate_limit_handler(request_limit):
    """Custom handler for rate limit breaches - returns JSON response."""
    from utils.core.errors import ErrorCategory, ErrorCode
    from utils.monitoring.observability_v2 import RATE_LIMIT_BREACHES

    endpoint = request.endpoint or "unknown"
    RATE_LIMIT_BREACHES.labels(endpoint=endpoint, limit_type="ip").inc()

    response = jsonify(
        {
            "error": "Terlalu banyak request",
            "code": ErrorCode.RATE_LIMIT_EXCEEDED,
            "category": ErrorCategory.RATE_LIMIT,
            "details": {"retry_after": 60},
        }
    )
    response.status_code = 429
    return response


limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    enabled=not _in_tests,
    default_limits=["200 per minute"],  # Lowered from 1000 for 1000+ concurrent users
    storage_uri=ratelimit_storage,
    strategy="fixed-window",
    on_breach=rate_limit_handler,
    swallow_errors=True,  # If Redis unavailable, allow request (don't block with error)
)


@limiter.request_filter
def _auth_flow_rate_limit_exempt():
    # Auth bootstrap must never be blocked by generic page/API bursts; otherwise
    # OAuth callback succeeds but /api/auth/me returns 429 and the UI shows
    # "Failed to load user info".
    return request.path == "/api/auth/me" or request.path.startswith("/api/auth/google/")


# ─── Correlation ID + JWT cache middleware ────────────────────────────────
@app.before_request
def add_correlation_id():
    g.correlation_id = str(uuid.uuid4())
    # BUG-21: Cache user_id here so after_request doesn't re-verify JWT
    g.user_id = None
    # Skip JWT verification for requests that never carry auth: CORS preflight
    # (OPTIONS), the public health endpoint, and static assets. Avoids needless
    # work and noise.
    if (
        request.method == "OPTIONS"
        or request.path.startswith("/api/health")
        or (request.endpoint == "static")
        or request.path.startswith("/static/")
    ):
        return
    try:
        verify_jwt_in_request(optional=True)
        identity = get_jwt_identity()
        if identity:
            g.user_id = int(identity)
            # Sliding window: mark for renewal if access token expires in < 1 hour
            try:
                claims = get_jwt()
                import time as _t
                remaining = int(claims.get("exp", 0)) - int(_t.time())
                g._renew_jwt = remaining < 3600  # < 1 hour left
                g._jwt_identity = identity
                g._jwt_claims = claims
            except Exception:
                g._renew_jwt = False
    except Exception as e:
        # Don't fail the request on a bad/expired token here (optional auth),
        # but don't swallow it silently either — log at debug for diagnostics.
        logging.debug("add_correlation_id: optional JWT verification failed: %s", e)


app.register_blueprint(auth)
app.register_blueprint(admin)
app.register_blueprint(simple_chat)
app.register_blueprint(drafts_bp)
app.register_blueprint(papers)
app.register_blueprint(files)
app.register_blueprint(paper_images)
app.register_blueprint(image_serve)
app.register_blueprint(chart_api)
app.register_blueprint(data_jobs)
app.register_blueprint(jobs)
app.register_blueprint(image_jobs)
app.register_blueprint(slr_api)  # literature endpoints (consolidated)
app.register_blueprint(quota)
app.register_blueprint(health)
app.register_blueprint(tools_api)
app.register_blueprint(logging_api)
app.register_blueprint(state_bp)
app.register_blueprint(doku_bp)    # DOKU SNAP payment endpoints (QRIS + VA)

# ─── Image generation provider health endpoint ─────────────────────
@app.route("/api/image-providers/status", methods=["GET"])
@jwt_required()
def image_providers_status():
    """Return health status of all image generation providers (API-first)."""
    from tools.image_generation.image_api_v2 import get_provider_status
    return jsonify(get_provider_status())


# ─── Observability routes: /metrics, /api/metrics, /api/healthz ───────────────
# main.py owns its own request/logging middleware, so we register only the
# observability ROUTES here (not the before/after_request hooks).
try:
    from utils.monitoring.observability_v2 import register_observability_routes

    register_observability_routes(app, db)
except Exception as _obs_err:  # pragma: no cover - defensive
    logging.getLogger(__name__).warning(
        "Failed to register observability routes: %s", _obs_err
    )


# ─── OpenAPI / Swagger UI ─────────────────────────────────────────────────
_OPENAPI_PATH = Path(__file__).parent / "openapi.yaml"


@app.route("/api/openapi.yaml", methods=["GET"])
@jwt_required()
def openapi_yaml():
    """Serve the OpenAPI 3.1 spec as YAML."""
    if not _OPENAPI_PATH.is_file():
        return jsonify({"error": "Spec not found"}), 404
    return send_file(_OPENAPI_PATH, mimetype="application/yaml")


_SWAGGER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>PaperFull API — Swagger UI</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css" />
  <style>body { margin:0; } .topbar { display:none; }</style>
</head>
<body>
  <div id="swagger"></div>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.onload = () => {
      window.ui = SwaggerUIBundle({
        url: "/api/openapi.yaml",
        dom_id: "#swagger",
        deepLinking: true,
        withCredentials: true,
        requestInterceptor: (req) => {
          // Forward CSRF for state-changing calls so try-it-out actually works.
          const m = (document.cookie.match(/(?:^|;\\s*)csrf_access_token=([^;]+)/) || [])[1];
          if (m && /^(POST|PUT|PATCH|DELETE)$/i.test(req.method || '')) {
            req.headers['X-CSRF-TOKEN'] = decodeURIComponent(m);
          }
          return req;
        },
      });
    };
  </script>
</body>
</html>"""


@app.route("/api/docs", methods=["GET"])
@jwt_required()
def api_docs():
    """Serve Swagger UI from CDN, pointed at /api/openapi.yaml."""
    return Response(_SWAGGER_HTML, mimetype="text/html")


# ─── Security headers ────────────────────────────────────────────────────────
@app.after_request
def _security_headers(response):
    # Use __setitem__ (overwrite) so we WIN over any middleware that sets
    # these first with restrictive values (e.g. Flask-Limiter default DENY).
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    # Content Security Policy — OVERWRITE any restrictive default (frame-ancestors 'none').
    csp = (
        "default-src 'self'; "
        # NOTE: 'unsafe-inline' in script-src is INTENTIONAL and REQUIRED for the
        # Vue SPA (inline bootstrap/hydration scripts). Removing it breaks the app.
        # Do not tighten this without migrating the frontend to nonces/hashes.
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; "
        "img-src 'self' data: https:; "
        "frame-src 'self' blob:; connect-src 'self'; "
        "font-src 'self' data:; "
        "frame-ancestors 'self'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    response.headers["Content-Security-Policy"] = csp
    # API responses should never be cached by intermediaries by default.
    if request.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")

    # Track rate limit metrics
    try:
        from utils.monitoring.observability_v2 import RATE_LIMIT_REQUESTS

        endpoint = request.endpoint or "unknown"
        status = "blocked" if response.status_code == 429 else "allowed"
        RATE_LIMIT_REQUESTS.labels(endpoint=endpoint, status=status).inc()
    except Exception:
        pass

    return response


# ─── Request access logging ───────────────────────────────────────────────────
@app.after_request
def _log_request(response):
    try:
        duration_ms = 0
        if hasattr(g, '_req_started_at'):
            duration_ms = (time.perf_counter() - g._req_started_at) * 1000
        # BUG-21: Read cached user_id from g instead of re-verifying JWT
        user_id = getattr(g, 'user_id', None)
        log_access(
            method=request.method,
            path=request.path,
            status=response.status_code,
            duration_ms=round(duration_ms, 2),
            user_id=user_id,
            ip=request.headers.get("X-Forwarded-For", request.remote_addr),
        )
    except Exception:
        pass
    return response


# ─── Sliding window: renew JWT cookies on every authenticated request ─────
@app.after_request
def _sliding_window_jwt(response):
    """If access token has <1h remaining, issue fresh cookies (24h sliding window)."""
    if getattr(g, "_renew_jwt", False) and g.user_id:
        try:
            from utils.database.models import User
            user = User.query.get(g.user_id)
            if user:
                claims = getattr(g, "_jwt_claims", {}) or {}
                new_access = create_access_token(
                    identity=str(user.id),
                    additional_claims={
                        "email": claims.get("email", user.email),
                        "name": claims.get("name", user.name),
                        "role": claims.get("role", user.role),
                        "avatar": claims.get("avatar", user.avatar_url or ""),
                    },
                )
                new_refresh = create_refresh_token(
                    identity=str(user.id),
                    additional_claims={"role": user.role},
                )
                set_access_cookies(response, new_access)
                set_refresh_cookies(response, new_refresh)
        except Exception:
            logging.debug("sliding_window_jwt: failed to renew tokens", exc_info=True)
    return response


# Stricter rate limit on auth endpoints to defend against credential stuffing.
limiter.limit("10 per minute")(auth)

# Rate limit expensive generation endpoints to prevent API exhaustion under load.
# Paper generation triggers AI API calls — limit to prevent overwhelming upstream.
# Note: ai_jobs_active is polled every 3s by frontend (20 req/min), so blanket limit
# must be high enough. Expensive endpoints have individual limits already.
limiter.limit("60 per minute")(jobs)

# Rate limit image generation — Playwright workers are very resource-intensive.
limiter.limit("10 per minute")(image_jobs)

# Rate limit AI tools endpoint — prevent abuse of expensive AI calls.
limiter.limit("30 per minute")(tools_api)

# ─── Logging Setup ────────────────────────────────────────────────────────────
from utils.core.global_logger import init_global_logging, log_access
_global_log = init_global_logging()
log = logging.getLogger(__name__)

# ─── Per-user data dirs ────────────────────────────────────────────────────
# Legacy UPLOAD_FOLDER/EXPORT_FOLDER retained only for backward-compat fallbacks.
# New uploads, charts, and exports use per-user paths via get_user_dir().
from utils.core.storage_helper import get_user_dir as _get_user_dir

UPLOAD_FOLDER = Path(__file__).parent / "user" / "uploads"
USER_BASE = Path(__file__).parent / "user"
USER_BASE.mkdir(exist_ok=True)

# Legacy export folder (kept for backward compat, new exports use per-user paths)
EXPORT_FOLDER = Path(__file__).parent / "data" / "exports"

TEMPLATE_FOLDER = Path(__file__).parent / "tools" / "Journal"

# Shared lock for all journal export adapters — prevents concurrent
# setattr→call→restore from clobbering module globals across different papers.
_ADAPTER_LOCK = threading.Lock()


def _available_journals():
    """Return canonical journal/template codes from *gen.py files in tools/Journal."""
    codes = []
    try:
        for gen_path in TEMPLATE_FOLDER.glob("*gen.py"):
            if gen_path.name.startswith("_"):
                continue
            if not gen_path.suffix == ".py":
                continue
            code = gen_path.stem[:-3]  # remove 'gen' suffix: "IEEEgen" -> "IEEE"
            if code:
                codes.append(code)
    except Exception:
        return []
    return sorted(set(codes), key=str.lower)


_JOURNAL_CODE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")

def _resolve_journal_code(raw: str | None) -> str:
    available = _available_journals()
    if not available:
        # No journal templates registered — fail loudly instead of returning a
        # bogus "IEEE" code that later blows up with an opaque ValueError.
        raise ValueError(
            "No journal templates available; cannot resolve journal code. "
            "Check journal template configuration."
        )
    if not raw:
        return "IEEE" if "IEEE" in available else available[0]
    raw_norm = str(raw).strip()
    if not raw_norm:
        return "IEEE" if "IEEE" in available else available[0]

    # Case-insensitive match to avoid client-side casing bugs
    m = {c.lower(): c for c in available}
    resolved = m.get(raw_norm.lower())
    if resolved:
        return resolved
    # Handle MDPI sub-journals: MDPI_acoustics → canonical 'MDPI'
    if raw_norm.lower().startswith('mdpi_') and len(raw_norm) > 5:
        if 'mdpi' in m:
            return 'MDPI'
        raise ValueError(f"MDPI journal template exists but sub-journal not resolved: {raw_norm!r}")
    # Unknown journal code — must match safe pattern to prevent import injection
    if not _JOURNAL_CODE_RE.match(raw_norm):
        raise ValueError(f"Invalid journal code: {raw_norm!r}")
    return raw_norm


def _count_inline_gambar(obj, depth=0) -> int:
    """Recursively count gambar items inside section content (including subsections)."""
    count = 0
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "content" and isinstance(v, list):
                for item in v:
                    if isinstance(item, dict) and item.get("id") in ("gambar", "image"):
                        count += 1
            if isinstance(v, (dict, list)):
                count += _count_inline_gambar(v, depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            count += _count_inline_gambar(item, depth + 1)
    return count


def _distribute_figures_to_sections(paper: dict):
    """Move items from paper['figures'] array into section content as inline
    {id: "gambar", ...} items so generators that only read section.content
    can render them.

    Distribution strategy: round-robin across sections that have content.
    Skips if inline gambar items already exist anywhere in the paper
    (including subsections), since those take precedence over the figures
    array which is often stale/empty.
    """
    figures = paper.get("figures", [])
    if not figures:
        return

    # Count existing inline gambar (recursive across all sections/subsections)
    existing_gambar = _count_inline_gambar(paper)
    if existing_gambar >= len(figures):
        return  # already has enough inline gambar, skip

    # Find sections with text content
    sections_with_content = []
    for sk in ["section1", "section2", "section3", "section4", "section5"]:
        s = paper.get(sk, {})
        c = s.get("content", [])
        if isinstance(c, list) and any(
            isinstance(item, dict) and item.get("id") == "text" and item.get("text")
            for item in c
        ):
            sections_with_content.append(sk)
        elif isinstance(c, str) and c.strip():
            sections_with_content.append(sk)

    if not sections_with_content:
        # No sections with content — use section2 as default
        sections_with_content = ["section2"]

    # Distribute figures round-robin
    for i, fig in enumerate(figures):
        if not isinstance(fig, dict):
            continue
        section_key = sections_with_content[i % len(sections_with_content)]
        s = paper[section_key]
        c = s.get("content", [])
        if not isinstance(c, list):
            c = []
            s["content"] = c

        inline_item = {
            "id": "gambar",
            "Title": fig.get("Title") or fig.get("title") or f"Figure {i+1}",
        }
        if fig.get("Prompt") or fig.get("prompt"):
            inline_item["Prompt"] = fig.get("Prompt") or fig.get("prompt")
        if fig.get("image_url"):
            inline_item["image_url"] = fig["image_url"]
        if fig.get("caption"):
            inline_item["caption"] = fig["caption"]
        # Copy Path + ImageNumber so DOCX generators can embed the image
        fig_path = fig.get("Path") or fig.get("path")
        if fig_path:
            inline_item["Path"] = fig_path
        fig_num = fig.get("ImageNumber") or fig.get("imageNumber")
        if fig_num:
            inline_item["ImageNumber"] = fig_num

        c.append(inline_item)


def _normalize_formulas(paper: dict) -> int:
    """Fix broken LaTeX in formula items across all sections/subsections.

    AI-generated content often produces LaTeX with missing backslashes
    (e.g. ``beginbmatrix`` instead of ``\\begin{bmatrix}``).  This
    normalises those commands so that ``latex2mathml`` can parse them.

    Also removes formula items whose ``latex`` field is empty — those
    would be silently skipped by generators, causing "Formula Missing"
    penalties from the checker.
    """
    import re as _re

    # LaTeX commands that MUST start with backslash
    _CMD_PREFIXES = (
        "frac", "sqrt", "int", "sum", "prod",
        "lim", "sin", "cos", "tan", "log", "ln", "exp",
        "alpha", "beta", "gamma", "delta", "theta", "lambda",
        "mu", "pi", "sigma", "omega", "phi", "psi", "xi",
        "cdot", "times", "pm", "mp", "div", "partial", "infty",
        "left", "right", "langle", "rangle",
        "bar", "hat", "tilde", "vec", "dot", "ddot",
        "text", "textbf", "mathrm", "mathcal",
        "subseteq", "supseteq", "in", "notin", "forall", "exists",
        "rightarrow", "leftarrow", "Rightarrow", "Leftarrow",
        "leq", "geq", "neq", "approx", "equiv", "sim", "propto",
        "begin", "end",
    )
    _CMD_PATTERN = _re.compile(
        r'(?<!\\)\b(' + '|'.join(_CMD_PREFIXES) + r')\b'
    )

    # Matrix/environment variants where the AI fused the command word
    # with the brace argument, e.g. "beginbmatrix" → "\\begin{bmatrix}"
    _MATRIX_FUSIONS = {
        "beginbmatrix": "\\begin{bmatrix}",
        "endbmatrix": "\\end{bmatrix}",
        "beginpmatrix": "\\begin{pmatrix}",
        "endpmatrix": "\\end{pmatrix}",
        "beginvmatrix": "\\begin{vmatrix}",
        "endvmatrix": "\\end{vmatrix}",
        "beginmatrix": "\\begin{matrix}",
        "endmatrix": "\\end{matrix}",
        "begincases": "\\begin{cases}",
        "endcases": "\\end{cases}",
        "beginaligned": "\\begin{aligned}",
        "endaligned": "\\end{aligned}",
        "begingathered": "\\begin{gathered}",
        "endgathered": "\\end{gathered}",
        "beginBmatrix": "\\begin{Bmatrix}",
        "endBmatrix": "\\end{Bmatrix}",
        "beginVmatrix": "\\begin{Vmatrix}",
        "endVmatrix": "\\end{Vmatrix}",
    }
    _FUSION_PATTERN = _re.compile(
        r'(?<!\\)(' + '|'.join(_re.escape(k) for k in _MATRIX_FUSIONS) + r')'
    )

    fixed = 0
    removed = 0

    def _walk(obj):
        nonlocal fixed, removed
        if isinstance(obj, dict):
            # Formula item?
            item_id = str(obj.get("id", "")).lower()
            if item_id in ("rumus", "equation", "formula", "persamaan"):
                latex = str(obj.get("latex", "")).strip()
                # Remove empty formulas
                if not latex:
                    return "REMOVE"
                # Fix matrix/environment fusions first
                new_latex = _FUSION_PATTERN.sub(lambda m: _MATRIX_FUSIONS[m.group(1)], latex)
                # Then fix regular missing backslashes
                new_latex = _CMD_PATTERN.sub(r'\\\1', new_latex)
                if new_latex != latex:
                    obj["latex"] = new_latex
                    fixed += 1
                return None

            # Recurse into dict values
            for key in list(obj.keys()):
                val = obj[key]
                if isinstance(val, (dict, list)):
                    result = _walk(val)
                    if result == "REMOVE":
                        # Remove from parent list (handled in list walk)
                        pass
                elif isinstance(val, list):
                    _clean_list(val)

        elif isinstance(obj, list):
            _clean_list(obj)

    def _clean_list(lst):
        nonlocal removed
        i = 0
        while i < len(lst):
            item = lst[i]
            if isinstance(item, (dict, list)):
                result = _walk(item)
                if result == "REMOVE":
                    del lst[i]
                    removed += 1
                    continue
            i += 1

    _walk(paper)
    if fixed or removed:
        import logging as _log
        _log.info("[normalize-formulas] Fixed %d LaTeX commands, removed %d empty formulas", fixed, removed)
    return fixed + removed


def _strip_ref_numbering(paper: dict) -> int:
    """Strip the ``[N]`` prefix from reference text items in-place.

    AI-generated paper data often stores references with numbers baked into
    the text field (e.g. ``"[1] Kadir, R. ..."``).  Most journal generators
    then add their own ``[i]`` prefix at output time, producing ``[1] [1] Kadir``.

    This function removes the leading ``[N] `` (or ``[N]``) so the generator's
    own numbering is the only one that appears.
    """
    import re as _re
    _REF_PREFIX = _re.compile(r'^\[\d+\][\s.]*')

    fixed = 0
    references = paper.get("references")
    if references is None:
        return 0

    if isinstance(references, list):
        iterable = enumerate(references)
    elif isinstance(references, dict):
        iterable = enumerate(references.get("content", []))
    else:
        return 0

    for _idx, item in iterable:
        if not isinstance(item, dict):
            old = str(item).strip()
            if old and _REF_PREFIX.match(old):
                item = _REF_PREFIX.sub("", old).strip()
                fixed += 1
            continue
        text_key = "text" if "text" in item else "Text"
        old = str(item.get(text_key, "")).strip()
        if old and _REF_PREFIX.match(old):
            new = _REF_PREFIX.sub("", old).strip()
            item[text_key] = new
            fixed += 1

    if fixed:
        import logging as _log
        _log.info("[normalize-refs] Stripped [N] prefix from %d references", fixed)
    return fixed


def _make_generate_adapter(mod, gen_fn):
    """Adapt a legacy ``generate()`` (no-arg, reads module-level globals) module
    into the ``build_document(json_path, output_path)`` interface used by the
    export route.

    These generators read their input/output paths from module globals
    (``TEMPLATE_JSON``/``JSON_PATH`` and ``OUTPUT_DOCX``/``OUTPUT_PATH``) and a
    ``load_json()`` helper that reads the global at call time. We temporarily
    rebind those globals so the export pipeline can drive arbitrary paths, then
    restore them so concurrent exports of different papers don't clobber each
    other.
    """
    INPUT_NAMES = ("TEMPLATE_JSON", "JSON_PATH", "INPUT_JSON", "DATA_JSON")
    OUTPUT_NAMES = ("OUTPUT_DOCX", "OUTPUT_PATH", "OUT_DOCX", "OUTPUT")

    def adapter(json_path, output_path=None):
        from pathlib import Path as _P
        # Normalize the JSON file before the generator reads it:
        # - Unwrap paper_data.paper so generators get flat structure
        # - Distribute figures array into section content as inline items
        _json_path = _P(json_path)
        try:
            with open(str(_json_path), "r", encoding="utf-8") as _f:
                _data = json.load(_f)
            _paper = _data
            was_wrapped = isinstance(_data, dict) and "paper_data" in _data
            if was_wrapped:
                pd = _data.get("paper_data", {})
                # Handle both old format (paper_data = flat) and new format (paper_data = {"paper": ...})
                _paper = pd.get("paper", pd) if isinstance(pd, dict) else _data
                # Inject figures/tables from paper_data level into paper for generator
                if isinstance(_paper, dict) and isinstance(pd, dict):
                    for key in ("figures", "tables", "equations"):
                        if key in pd and key not in _paper:
                            _paper[key] = pd[key]
            if isinstance(_paper, dict) and "figures" in _paper:
                _distribute_figures_to_sections(_paper)
            # Always save the modified version so generators see distributed figures
            # when the data isn't wrapped in paper_data.
            _to_save = _paper
            with open(str(_json_path), "w", encoding="utf-8") as _f:
                json.dump(_to_save, _f, ensure_ascii=False, indent=2)
        except Exception:
            log.warning("JSON normalization failed for %s: could not save modified paper", _json_path)
        with _ADAPTER_LOCK:
            in_name = next((n for n in INPUT_NAMES if hasattr(mod, n)), None)
            out_name = next((n for n in OUTPUT_NAMES if hasattr(mod, n)), None)
            saved = {}
            if in_name:
                saved[in_name] = getattr(mod, in_name)
                setattr(mod, in_name, _P(json_path))
            if out_name:
                saved[out_name] = getattr(mod, out_name)
                if output_path is not None:
                    setattr(mod, out_name, _P(output_path))
            try:
                result = gen_fn()
            finally:
                for k, v in saved.items():
                    setattr(mod, k, v)
        if output_path is not None:
            return _P(output_path)
        if result is not None:
            return result
        return _P(getattr(mod, out_name)) if out_name else None

    return adapter


def _get_builder_for_journal(journal_code: str):
    """Return ``(canonical_code, build_document_fn, build_pdf_fn | None)``
    for a known template code.

    ``build_pdf_fn`` is the gen's own ``build_pdf(json_path, pdf_path)`` if
    available; otherwise *None* (caller falls back to LibreOffice).

    Template lookup is cached — changes to template files require a restart.
    """
    # Security: reject codes with dots, slashes, or other special chars that could
    # lead to arbitrary module imports (e.g. "..os" → import os)
    if not _JOURNAL_CODE_RE.match(journal_code):
        raise ValueError(f"Invalid journal code (special chars not allowed): {journal_code!r}")
    available = _available_journals()
    m = {c.lower(): c for c in available}
    canonical = m.get(journal_code.lower())
    if not canonical:
        raise ValueError(f"Unknown journal template: {journal_code}")
    with _ADAPTER_LOCK:
        mod = importlib.import_module(f"tools.Journal.{canonical}gen")
        # ponytail: importlib.reload removed — cached for performance.
        # Add back if hot-reload of template generators is needed in prod.

    pdf_builder = getattr(mod, "build_pdf", None)

    builder = getattr(mod, "build_document", None)
    if callable(builder):
        return canonical, builder, pdf_builder
    gen_fn = getattr(mod, "generate", None)
    if callable(gen_fn):
        return canonical, _make_generate_adapter(mod, gen_fn), pdf_builder
    raise ValueError(f"Template generator missing build_document/generate: {canonical}gen")


AIOTOMASI_MODEL = get_primary_generate_model()

# Initialize shared job helpers so background threads can use them.
_init_job_core(app, AIOTOMASI_MODEL)

# ─── DB Init ──────────────────────────────────────────────────────────────────
with app.app_context():
    db.create_all()
    log.info("Database tables created/verified")


# ─── AiJob sweeper (mark stuck pending jobs as errored) ──────────────────────
AIJOB_PENDING_TIMEOUT_SECONDS = 15 * 60  # 15 minutes


def _sweep_stuck_jobs():
    """Best-effort: mark AiJob rows stuck in 'pending' or 'running' beyond the
    timeout as errored so the frontend stops polling forever after a worker crash.
    Also recovers jobs left in 'running' after a server restart (daemon threads
    killed by SIGTERM). Safe under multi-worker because UPDATEs are conditional.
    Only one worker runs the sweeper via Redis distributed lock (BUG-15).
    """
    _SWEEP_LOCK_KEY = "papergenerator:sweeper_lock"
    _SWEEP_LOCK_TTL = 120  # seconds

    while True:
        try:
            time.sleep(60)

            # Distributed lock: only one worker runs each sweep iteration
            from utils.core.redis_client import get_redis
            rc = get_redis()
            lock_acquired = False
            lock_token = None
            if rc is not None:
                import uuid as _uuid
                lock_token = str(_uuid.uuid4())
                acquired = rc.set(_SWEEP_LOCK_KEY, lock_token, nx=True, ex=_SWEEP_LOCK_TTL)
                if not acquired:
                    continue  # another worker holds the lock, skip this iteration
                lock_acquired = True
            # If Redis unavailable (fallback), fall through — original behavior

            try:
                with app.app_context():
                    # Pending jobs stuck > 15 min
                    cutoff = datetime.now(timezone.utc) - _td(
                        seconds=AIJOB_PENDING_TIMEOUT_SECONDS
                    )
                    stuck = AiJob.query.filter(
                        AiJob.status == "pending",
                        AiJob.started_at < cutoff,
                    ).all()
                    # Running jobs stuck > 30 min (covers post-restart recovery)
                    running_cutoff = datetime.now(timezone.utc) - _td(seconds=30 * 60)
                    stuck_running = AiJob.query.filter(
                        AiJob.status == "running",
                        AiJob.started_at < running_cutoff,
                    ).all()
                    all_stuck = stuck + stuck_running
                    if not all_stuck:
                        continue
                    stuck_ids = [j.id for j in all_stuck]
                    AiJob.query.filter(
                        AiJob.id.in_(stuck_ids),
                        AiJob.status.in_(["pending", "running"]),
                    ).update(
                        {
                            "status": "error",
                            "error": "Job stuck — worker likely crashed or server restarted",
                            "timeout": True,
                        },
                        synchronize_session=False,
                    )
                    safe_commit()
                    log.warning(
                        "Swept %d stuck AI jobs (%d pending, %d running)",
                        len(all_stuck), len(stuck), len(stuck_running),
                    )
            finally:
                # Explicitly release the Redis lock (safe: only delete if token matches)
                if lock_acquired and rc is not None and lock_token:
                    try:
                        _release_lua = "if redis.call('get',KEYS[1])==ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end"
                        rc.eval(_release_lua, 1, _SWEEP_LOCK_KEY, lock_token)
                    except Exception:
                        pass  # TTL will expire anyway; best-effort release
        except Exception:
            log.exception("AiJob sweeper iteration failed")


threading.Thread(target=_sweep_stuck_jobs, daemon=True, name="aijob-sweeper").start()

# ─── Image generation worker pool (4 workers, 1 per Gemini account) ──────
# MOVED to gunicorn.conf.py post_fork hook. Starting threads at module level
# with preload_app=True causes 'Event' object is not callable errors after
# gunicorn forks workers. The post_fork hook starts workers cleanly.

# ─── SLR orchestrator — lightweight in-memory, no DB-polling worker ──────
# The new slr.py uses ThreadPoolExecutor directly on each POST request.
# No background worker pool needed. Legacy worker.py moved to eks/.
log.info("SLR orchestrator active (in-memory, no DB-polling worker)")

# ─── Health Check ────────────────────────────────────────────────────────────
# NOTE: The /api/health endpoint is served by the `health` Blueprint
# (utils.health, url_prefix='/api/health', returns {"status": "healthy", ...}).
# A previous app-level `def health()` here registered the SAME /api/health route
# AND collided with the Blueprint's name in the import namespace. It was removed
# as redundant — do not re-add an app-level /api/health route.


# ─── AI Generate (Section) ───────────────────────────────────────────────────


@app.route("/api/generate", methods=["POST"])
@limiter.limit("20 per minute")  # AI calls are expensive; 20/min per IP
@jwt_required()
def generate():
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        prompt = data.get("prompt", "")
        last_text = data.get("lastText", "")
        paper_context = data.get("paperContext", {})
        section = data.get("section", "").lower()

        if not prompt:
            return jsonify({"error": "Prompt is required"}), 400

        # AI Mocking for testing (rate limiting still enforced by decorator)
        try:
            from tests.helpers.mock_ai import get_mock_generate_response, should_mock_ai
            if should_mock_ai():
                mock_response = get_mock_generate_response(prompt=prompt, section=section)
                return jsonify(mock_response)
        except ImportError:
            pass

        from utils.ai_tools.model_config import get_endpoint_chain
        _chain = get_endpoint_chain(heavy=True)
        if not _chain:
            return jsonify({"error": "AIOTOMASI endpoint not configured (set AIOTOMASI_API{1,2,3} + AIOTOMASI_APIKEY{1,2,3})"}), 500
        # Per-index chain resolves the endpoint+key internally; pass slot-1 as
        # legacy fallback args.
        primary_model, base_url, api_key = _chain[0]

        prompts_by_section = {
            "title": "You are an IEEE conference paper title writer. Generate a concise, specific paper title (max 15 words). Return ONLY the title.",
            "abstract": "You are an IEEE conference paper writer. Generate a 150-200 word abstract. Start with problem statement, then method, then results. Return ONLY the abstract text.",
            "introduction": "You are an IEEE conference researcher. Write an INTRODUCTION section (200-300 words): 1) Motivate the problem 2) Identify research gap 3) State contributions. Include citations as [1], [2].",
            "methodology": "You are a systems researcher. Write a METHODOLOGY section describing: 1) Problem formulation 2) Proposed method/algorithm 3) Implementation details. Use IEEE notation.",
            "results": "You are a research scientist. Write EXPERIMENTAL RESULTS: 1) Datasets used 2) Metrics with values 3) Comparison with baselines 4) Analysis.",
            "conclusion": "You are an academic writer. Write CONCLUSION (100-150 words): 1) Summarize contributions 2) Highlight metrics 3) Future work.",
            "acknowledgment": "Write 2-3 sentences of paper acknowledgments thanking funding agencies, collaborators. Professional and concise.",
        }

        system_prompt = prompts_by_section.get(
            section,
            "You are an expert academic writer for IEEE papers. Generate content for the specified section. Use LaTeX notation for formulas. Return ONLY the content.",
        )

        messages = [{"role": "system", "content": system_prompt}]
        context_parts = []
        if paper_context:
            context_parts.append(f"Paper title: {paper_context.get('title', 'Untitled')}")
            if paper_context.get("abstract"):
                context_parts.append(f"Abstract: {paper_context['abstract'][:500]}")
        if last_text:
            context_parts.append(f"\n--- Current content ---\n{last_text}\n--- End ---")
        if context_parts:
            messages.append({"role": "user", "content": "\n".join(context_parts)})
            messages.append(
                {
                    "role": "assistant",
                    "content": "I understand the context. What would you like me to do?",
                }
            )
        messages.append({"role": "user", "content": prompt})

        from tools.editor.api_client import _call_aiotomasi_with_fallback  # noqa: PLC0415

        result, model_used = _call_aiotomasi_with_fallback(
            messages,
            api_key,
            base_url,
            AIOTOMASI_MODEL,
        )
        # Upstream SSE doesn't return token counts; report char-derived estimate
        # so the frontend keeps its existing usage shape without claiming false
        # token totals. _log_api_usage records 0/0/0 which is harmless.
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        user_id = _get_current_user_id()
        threading.Thread(
            target=_log_api_usage, args=("generate", usage, user_id), daemon=True
        ).start()
        return jsonify(
            {
                "success": True,
                "content": result,
                "text": result,
                "model": model_used,
                "usage": usage,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        log.exception("unhandled error")
        return jsonify({"error": "Internal server error"}), 500


# ─── Generate Full Paper ─────────────────────────────────────────────────────


def _extract_texts_from_files(files):
    """Extract text from uploaded files (PDF/DOCX/Excel/CSV). Returns list of text strings."""
    import tempfile
    texts = []
    for f in files:
        if not f.filename:
            continue
        ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
        tmp_path = None
        try:
            suffix = '.' + ext
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                f.save(tmp)
                tmp_path = tmp.name
            text = ''
            if ext == 'pdf':
                try:
                    import pymupdf
                    with pymupdf.open(tmp_path) as doc:
                        text = '\n'.join(page.get_text() for page in doc)
                except ImportError:
                    try:
                        from pdfminer.high_level import extract_text
                        text = extract_text(tmp_path) or ''
                    except ImportError:
                        text = f'[PDF extraction unavailable for {f.filename}]'
            elif ext in ('docx', 'doc'):
                try:
                    from docx import Document
                    doc = Document(tmp_path)
                    text = '\n'.join(p.text for p in doc.paragraphs)
                except ImportError:
                    text = f'[DOCX extraction unavailable for {f.filename}]'
            elif ext in ('xlsx', 'xls'):
                try:
                    import openpyxl
                    wb = openpyxl.load_workbook(tmp_path, read_only=True, data_only=True)
                    try:
                        md_lines = []
                        for sheet_name in wb.sheetnames:
                            ws = wb[sheet_name]
                            md_lines.append(f'### Sheet: {sheet_name}\n')
                            rows = []
                            for row in ws.iter_rows(values_only=True):
                                rows.append([str(c) if c is not None else '' for c in row])
                            if rows:
                                # Build markdown table
                                header = rows[0]
                                md_lines.append('| ' + ' | '.join(header) + ' |')
                                md_lines.append('| ' + ' | '.join(['---'] * len(header)) + ' |')
                                for row in rows[1:]:
                                    # Pad row to match header columns
                                    while len(row) < len(header):
                                        row.append('')
                                    md_lines.append('| ' + ' | '.join(row[:len(header)]) + ' |')
                            md_lines.append('')
                        text = '\n'.join(md_lines)
                    finally:
                        wb.close()
                except ImportError:
                    text = f'[Excel extraction unavailable for {f.filename}]'
            elif ext == 'csv':
                with open(tmp_path, 'r', encoding='utf-8', errors='replace') as csvf:
                    text = csvf.read()
            else:
                text = f'[Unsupported file type: {ext} for {f.filename}]'

            if text.strip():
                header = f'\n\n=== Extracted from: {f.filename} ===\n'
                texts.append(header + text[:20000])  # cap per file at 20k chars
        except Exception as e:
            log.warning("Failed to extract text from %s: %s", f.filename, e)
            texts.append(f'\n\n=== Extracted from: {f.filename} ===\n[Extraction failed: {e}]')
        finally:
            # BUG-16: Always clean up temp file, even if extraction raised
            if tmp_path:
                try:
                    import os as _os
                    _os.unlink(tmp_path)
                except Exception:
                    pass
    return texts


def _wait_for_images(paper_id, user_id, timeout_s=900):
    """Block generate-full completion until image jobs are no longer queued/running."""
    from utils.database.models import ImageGenJob  # noqa: PLC0415

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        with app.app_context():
            pending = ImageGenJob.query.filter(
                ImageGenJob.paper_id == paper_id,
                ImageGenJob.user_id == int(user_id),
                ImageGenJob.status.in_(["queued", "running"]),
            ).count()
        if pending == 0:
            return
        time.sleep(5)
    log.warning("image generation wait timed out for paper_id=%s", paper_id)


def _run_generate_full_job(
    job_id,
    prompt,
    user_id=None,
    topic=None,
    style=None,
    pdf_texts=None,
    custom_prompt=None,
    paper_id=None,
    conv_id=None,
    resume_state=None,
    language=None,
    **_legacy_kwargs,
):
    """Generate a full paper via single-shot generation.

    Legacy callers may still pass ``model=`` or ``chunked=`` — both are now
    silently ignored. The model is read from MODELGENERATE env var (VIOLA-GENERATE).
    See paper_generation/single.py for implementation details.
    """
    t_start = time.time()
    log.info("[job:%s] started, prompt=%r (single-shot generation)", job_id, prompt[:80])

    # ── Progress ticker: 0→95% over 15 minutes (900s), jumps to 100% on done ──
    _ticker_stop = threading.Event()
    def _progress_ticker():
        """Tick progress from 5% to 95% over 900s (15 min). Stops when event set."""
        elapsed = 0
        while not _ticker_stop.wait(timeout=10):
            elapsed += 10
            pct = min(95, 5 + int((elapsed / 900.0) * 90))
            try:
                with app.app_context():
                    j = AiJob.query.filter_by(id=job_id).first()
                    if j and j.status == "running":
                        j.progress = pct
                        safe_commit()
                _publish("generating", pct, "running")
            except Exception:
                try:
                    db.session.rollback()
                except Exception:
                    pass
    _ticker_thread = threading.Thread(target=_progress_ticker, daemon=True)

    if _legacy_kwargs:
        log.info("[job:%s] ignoring legacy kwargs: %s", job_id, sorted(_legacy_kwargs.keys()))
    uid = None
    try:
        uid = int(user_id) if user_id is not None else None
    except Exception:
        uid = None

    # ── checkpoint + cancel wiring ─────────────────────────────────────────
    # In single-shot mode we still maintain the AiJob row + Redis SSE channel
    # so existing UI code keeps working. The single round-trip means there's
    # no mid-flight checkpoint cadence — we publish "running" once at start
    # and "complete" once at the end. Cancellation is checked once before we
    # call out so a user who hit Cancel before the API was reached is honoured.
    def _publish(stage, percent, status):
        try:
            from tools.paperfull.jobs import publish_progress

            publish_progress(
                job_id,
                {
                    "stage": stage,
                    "percent": int(percent),
                    "status": status,
                },
            )
        except Exception:
            pass

    def _cancel_check():
        try:
            with app.app_context():
                j = AiJob.query.filter_by(id=job_id).first()
                return bool(j and j.status == "cancelled")
        except Exception:
            return False

    def _checkpoint(stage, progress):
        try:
            with app.app_context():
                j = AiJob.query.filter_by(id=job_id).first()
                if not j:
                    return
                j.stage = stage
                j.progress = max(0, min(100, int(progress)))
                safe_commit()
        except Exception:
            try:
                db.session.rollback()
            except Exception:
                pass
            log.exception("[job:%s] checkpoint failed at stage=%s", job_id, stage)
        _publish(stage, progress, "running" if int(progress) < 100 else "complete")

    paper_data = None  # scoped so except handlers can persist partial content

    try:
        from utils.ai_tools.model_config import get_endpoint_chain
        if not get_endpoint_chain(heavy=True):
            raise Exception("AIOTOMASI endpoint not configured (set AIOTOMASI_API{1,2,3} + AIOTOMASI_APIKEY{1,2,3})")

        extra_parts = []
        if custom_prompt:
            extra_parts.append(custom_prompt)
        if pdf_texts:
            combined = "\n\n".join(pdf_texts[:5])
            extra_parts.append(f"[REFERENCE DOCUMENTS]\n{combined}")
        extra = ("\n\n".join(extra_parts)).strip()

        # Pre-flight cancel check — honour the user pressing Cancel before we
        # hit the upstream API. Mirrors the behaviour of the chunked path.
        if _cancel_check():
            raise GenerationCancelled("start")

        _checkpoint("generating", 5)

        # Start progress ticker (5%→95% over 15 min)
        _ticker_thread.start()

        # Save send.json to paperfull history
        if uid is not None and paper_id:
            try:
                from utils.core.user_storage import get_username, save_paperfull_send_by_id
                username = get_username(user_id=uid)
                save_paperfull_send_by_id(username, paper_id, {
                    "job_id": job_id,
                    "prompt": prompt[:4000],
                    "topic": topic,
                    "style": style,
                    "has_pdf_texts": bool(pdf_texts),
                })
            except Exception:
                log.warning("[job:%s] Could not save paperfull send.json", job_id, exc_info=True)

        paper_data = generate_paper_json_single(
            judul=prompt,
            custom_prompt=extra,
            topic=topic,
            style=style,
            language=language or "id",
            paper_id=paper_id,
            conv_id=conv_id,
            job_id=job_id,
            user_id=user_id,
        )

        # Inject resolved language so it persists in paper.data after save.
        # _normalize_paper_shape doesn't include language in its output.
        if language:
            paper_data["language"] = language

        # ── PARTIAL SAVE: persist raw paper_data to Paper.data immediately ──
        # If the worker crashes, gets killed, or hits any error after this point
        # the user at least keeps the content the model already returned.
        if uid is not None and paper_id:
            try:
                with app.app_context():
                    paper = Paper.query.filter_by(id=paper_id, user_id=uid).first()
                    if paper:
                        partial = dict(paper_data)
                        partial["_partial"] = True
                        # Preserve metadata that generation output doesn't include
                        _ex = paper.data if isinstance(paper.data, dict) else {}
                        for _mk in ('language', 'journal', 'citation_style'):
                            if _mk not in partial and _mk in _ex:
                                partial[_mk] = _ex[_mk]
                        paper.data = partial
                        paper.title = (
                            (paper_data.get("title") or "").strip()
                            or paper.title
                            or "Untitled"
                        )
                        paper.updated_at = datetime.now(timezone.utc)
                        safe_commit()
                        log.info("[job:%s] partial content saved to paper %s", job_id, paper_id)
            except Exception:
                try:
                    db.session.rollback()
                except Exception:
                    pass
                log.exception("[job:%s] failed to persist partial content to paper %s", job_id, paper_id)

        # Validate that the model returned a complete paper before persisting.
        # Without this, an upstream truncation (e.g. the model stopped at
        # section1 because of `max_tokens`) silently produces a stub paper that
        # only the user discovers after waiting 5–10 minutes.
        from tools.editor.single import _validate_paper_shape as _vps

        validation = _vps(paper_data)
        if not validation["ok"]:
            log.warning(
                "[job:%s] generated paper INCOMPLETE: %s",
                job_id,
                validation["issues"],
            )
            # We still save the partial result (better than nothing), but mark
            # the job stage so the chat surfaces the issue rather than
            # silently calling it "done".
            try:
                with app.app_context():
                    j = AiJob.query.filter_by(id=job_id).first()
                    if j:
                        existing = (j.error or "").strip()
                        warn = "Generated paper incomplete: " + ", ".join(validation["issues"])
                        j.error = (existing + "\n" if existing else "") + warn
                        safe_commit()
            except Exception as _ve:
                log.warning("Failed to save validation warning for paper %s: %s", paper_id, _ve)

        paper_data.setdefault(
            "authors",
            [
                {
                    "name": "Author Name",
                    "affiliation": "Department, University",
                    "location": "City, Country",
                    "email": "author@example.com",
                }
            ],
        )
        paper_data.setdefault("keywords", [])
        paper_data.setdefault("sections", [])
        paper_data.setdefault("acknowledgment", "")
        paper_data.setdefault("references", [])
        paper_data.setdefault("figures", [])
        paper_data.setdefault("tables", [])
        paper_data.setdefault("equations", [])

        for auth in paper_data["authors"]:
            auth.setdefault("name", "")
            auth.setdefault("affiliation", "")
            auth.setdefault("location", "")
            auth.setdefault("email", "")

        for i, sec in enumerate(paper_data["sections"]):
            sec.setdefault("id", f"id-sec{i+1}")
            sec.setdefault("number", "")
            sec.setdefault("title", "")
            sec.setdefault("content", "")
            sec.setdefault("subsections", [])
            for j, sub in enumerate(sec["subsections"]):
                sub.setdefault("id", f"id-sub{i+1}{chr(97+j)}")
                sub.setdefault("letter", chr(65 + j))
                sub.setdefault("title", "")
                sub.setdefault("content", "")
                sub.setdefault("numberedItems", [])

        for i, fig in enumerate(paper_data["figures"]):
            fig.setdefault("id", f"figure-{i+1}")
            fig.setdefault("caption", f"Fig. {i+1}. ")
            fig.setdefault("filename", "")
            fig.setdefault("url", "")

        for i, tbl in enumerate(paper_data["tables"]):
            tbl.setdefault("id", f"table-{i+1}")
            tbl.setdefault("caption", f"TABLE {i+1}. ")
            tbl.setdefault("headers", [])
            tbl.setdefault("rows", [])

        for i, eq in enumerate(paper_data["equations"]):
            eq.setdefault("id", f"eq-{i+1}")
            eq.setdefault("latex", "")
            eq.setdefault("number", i + 1)

        try:
            output_dir = Path(__file__).parent / "output"
            output_dir.mkdir(exist_ok=True)
            safe_title = re.sub(r"[^a-zA-Z0-9_]", "_", prompt[:50]).strip("_")
            ts_str = time.strftime("%Y%m%d_%H%M%S")
            json_out = output_dir / f"{ts_str}_{safe_title}.json"
            json_out.write_text(
                json.dumps(paper_data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as save_err:
            log.warning("[job:%s] Could not save JSON: %s", job_id, save_err)

        # Save paper.json to user storage
        if uid is not None:
            try:
                from utils.core.user_storage import get_username, save_paper_json, save_paper_json_by_id
                username = get_username(user_id=uid)
                paper_title = (paper_data.get("title") or "").strip() or prompt[:60]
                if paper_id:
                    save_paper_json_by_id(username, paper_id, paper_data)
                else:
                    save_paper_json(username, paper_title, paper_data)
            except Exception:
                log.warning("[job:%s] Could not save paper.json to user storage", job_id, exc_info=True)

        # Stop progress ticker
        _ticker_stop.set()

        # ── Token deduction for Generate Full (fallback single-shot path) ────
        # This mirrors the deduction in paper_worker.py chunked path.
        if uid is not None and paper_data:
            try:
                from utils.database.models import ApiUsageLog, User as _User
                prompt_text = "\n".join(str(x or "") for x in (prompt, extra, topic, style, language))
                completion_text = json.dumps(paper_data, ensure_ascii=False)
                prompt_tokens = max(1, len(prompt_text) // 4)
                completion_tokens = max(1, len(completion_text) // 4)
                total_tokens = prompt_tokens + completion_tokens
                # Streaming/fallback providers often omit reasoning usage; Generate Full
                # has a minimum internal charge after a successful save.
                if total_tokens < 120_000:
                    completion_tokens += 120_000 - total_tokens
                    total_tokens = 120_000
                db.session.add(ApiUsageLog(
                    user_id=int(uid),
                    endpoint="/api/papers/generate-full",
                    model="VIOLA-GENERATE",
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    created_at=datetime.now(timezone.utc),
                ))
                _user = _User.query.get(int(uid))
                if _user and _user.role != "admin":
                    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
                    if (_user.usage_month_key or "") != month_key:
                        _user.usage_month_key = month_key
                        _user.token_used_month = 0
                    _user.token_used_month = int(_user.token_used_month or 0) + total_tokens
                safe_commit()
            except Exception:
                try:
                    db.session.rollback()
                except Exception:
                    pass

        # Before final checkpoint: auto-enqueue figure images + wait until they finish
        # so progress bar only hits 100% once images are generated.
        if uid is not None and paper_id:
            _checkpoint("generating_figures", 95)
            try:
                from tools.paperfull.paper_worker import _auto_enqueue_figure_images
                _auto_enqueue_figure_images(paper_id, int(uid), paper_data)
                _wait_for_images(paper_id, uid)
                # BUG-FIX: reconcile generated image paths back into paper_data
                # BEFORE persisting to DB, so the editor sees real .jpg paths
                # instead of the placeholder .png prompts.
                # Two targets: top-level figures[] + section gambar items.
                try:
                    from tools.editor.utils import safe_paper_image_dir
                    from tools.image_generation.reconcile import reconcile_figure_images
                    from tools.paperfull.jobs import _reconcile_section_images
                    _upl = safe_paper_image_dir(paper_id)
                    if _upl and _upl.exists():
                        reconcile_figure_images(paper_id, paper_data, _upl.parent)
                        _reconcile_section_images(paper_data, paper_id, _upl.parent)
                        log.info("[job:%s] reconciled %d figures + %d section images",
                                 job_id,
                                 len(paper_data.get("figures", [])),
                                 sum(1 for s in paper_data.get("sections", [])
                                     for c in s.get("content", []) if c.get("id") == "gambar"))
                except Exception:
                    log.warning("[job:%s] image path reconciliation failed", job_id, exc_info=True)
            except Exception:
                log.exception("[job:%s] auto-enqueue figures failed", job_id)

        # Single end-of-run checkpoint — stage="complete", progress=100.
        _checkpoint("complete", 100)

        # Save recv.json to paperfull history
        if uid is not None and paper_id:
            try:
                from utils.core.user_storage import get_username, save_paperfull_recv_by_id
                username = get_username(user_id=uid)
                save_paperfull_recv_by_id(username, paper_id, {
                    "job_id": job_id,
                    "status": "done",
                    "title": (paper_data.get("title") or "").strip(),
                    "sections_count": len(paper_data.get("sections", [])),
                    "references_count": len(paper_data.get("references", [])),
                    "elapsed_seconds": int(time.time() - t_start),
                })
            except Exception:
                log.warning("[job:%s] Could not save paperfull recv.json", job_id, exc_info=True)

        elapsed = time.time() - t_start
        _log_api_usage(
            "generate-full",
            {"total_tokens": 0, "prompt_tokens": 0, "completion_tokens": 0},
            user_id,
        )
        with app.app_context():
            # Persist into Paper.data when chat-tool flow gave us a paper_id —
            # this prevents the result being lost if the one-shot /api/job
            # response is consumed before the editor reloads the paper.
            if paper_id and uid is not None:
                try:
                    paper = Paper.query.filter_by(id=paper_id, user_id=uid).first()
                    if paper:
                        # Remove _partial flag — this is the final, complete paper
                        paper_data.pop("_partial", None)
                        # Preserve metadata that generation output doesn't include
                        _ex = paper.data if isinstance(paper.data, dict) else {}
                        for _mk in ('language', 'journal', 'citation_style'):
                            if _mk not in paper_data and _mk in _ex:
                                paper_data[_mk] = _ex[_mk]
                        paper.data = paper_data
                        paper.title = (
                            (paper_data.get("title") or "").strip()
                            or paper.title
                            or "Untitled"
                        )
                        paper.updated_at = datetime.now(timezone.utc)
                        safe_commit()
                        log.info("[job:%s] persisted into paper %s", job_id, paper_id)
                except Exception:
                    db.session.rollback()
                    log.exception("[job:%s] failed to persist into paper %s", job_id, paper_id)
            if uid is not None:
                _job_set_done(job_id, uid, paper_data, int(elapsed))
        log.info("[job:%s] DONE in %.1fs", job_id, elapsed)

    except GenerationCancelled as gc:
        # Stop progress ticker
        _ticker_stop.set()
        # Cooperative cancel: persist whatever was already checkpointed and
        # mark the job cancelled (so the UI bubble can surface the partial
        # result + a Resume button).
        elapsed = time.time() - t_start
        log.info("[job:%s] CANCELLED at stage=%s after %.1fs", job_id, gc.stage, elapsed)
        with app.app_context():
            try:
                j = AiJob.query.filter_by(id=job_id).first()
                if j:
                    j.status = "cancelled"
                    j.stage = gc.stage
                    existing = j.result if isinstance(j.result, dict) else {}
                    j.result = {
                        **existing,
                        "cancelled_at_stage": gc.stage,
                        "elapsed_seconds": int(elapsed),
                    }
                    safe_commit()
            except Exception:
                db.session.rollback()
                log.exception("[job:%s] failed to persist cancellation", job_id)
        try:
            from tools.paperfull.jobs import publish_progress

            publish_progress(job_id, {"stage": gc.stage, "status": "cancelled"})
        except Exception:
            pass

    except Exception as e:
        # Stop progress ticker
        _ticker_stop.set()
        elapsed = time.time() - t_start
        err_str = str(e)
        timeout_flag = (
            "timeout" in type(e).__name__.lower()
            or "timeout" in err_str.lower()
            or "timed out" in err_str.lower()
        )
        log.error("[job:%s] FAILED after %.1fs: %s", job_id, elapsed, e, exc_info=True)
        with app.app_context():
            if uid is not None:
                _job_set_error(
                    job_id,
                    uid,
                    (
                        f"Generation timed out after {int(elapsed)}s. Try a shorter topic."
                        if timeout_flag
                        else "Generation failed due to internal error. Please try again."
                    ),
                    timeout_flag=timeout_flag,
                )
            # ── Preserve partial content in Paper.data on error ──
            # The early partial save (right after the API returned) already
            # wrote the content to Paper.data. Here we just add error metadata
            # so the frontend can surface it. If paper_data is None the API
            # call never returned — nothing to preserve.
            if paper_id and uid is not None and paper_data is not None:
                try:
                    paper = Paper.query.filter_by(id=paper_id, user_id=uid).first()
                    if paper and paper.data:
                        paper.data["_partial"] = True
                        paper.data["_generation_error"] = err_str[:500]
                        paper.updated_at = datetime.now(timezone.utc)
                        safe_commit()
                        log.info(
                            "[job:%s] partial content preserved in paper %s after error",
                            job_id, paper_id,
                        )
                except Exception:
                    try:
                        db.session.rollback()
                    except Exception:
                        pass
                    log.exception(
                        "[job:%s] failed to annotate partial paper %s with error",
                        job_id, paper_id,
                    )
    finally:
        # Always stop the progress ticker so the background thread can exit —
        # the per-path .set() calls above don't cover every early-return / raise
        # site, and without this a thread could leak (join below would block its
        # full timeout). Setting an already-set Event is a harmless no-op.
        _ticker_stop.set()
        _ticker_thread.join(timeout=2)


@app.route("/api/generate-full", methods=["POST"])
@limiter.limit("10 per minute")  # Full paper generation: heavier, stricter limit
@jwt_required()
def generate_full():
    try:
        # Support both JSON and multipart/form-data (for file uploads)
        pdf_texts = []
        if request.content_type and 'multipart/form-data' in request.content_type:
            prompt = (request.form.get("prompt") or "").strip()
            topic = request.form.get("topic") or None
            style = request.form.get("style") or None
            paper_id = request.form.get("paper_id") or None
            conv_id = request.form.get("conv_id") or None
            model = request.form.get("model") or None

            # Extract text from uploaded files (PDF/DOCX/Excel/CSV)
            uploaded_files = request.files.getlist("files")
            if uploaded_files:
                pdf_texts = _extract_texts_from_files(uploaded_files)
        else:
            data = request.get_json(silent=True)
            if not data:
                return jsonify({"error": "No JSON data provided"}), 400
            prompt = data.get("prompt", "").strip()
            topic = data.get("topic") or None
            style = data.get("style") or None
            pdf_texts = data.get("pdf_texts") or []
            paper_id = data.get("paper_id") or None
            conv_id = data.get("conv_id") or None
            model = data.get("model") or None

        if not prompt:
            return jsonify({"error": "Prompt is required"}), 400

        # AI Mocking for testing (rate limiting still enforced by decorator)
        try:
            from tests.helpers.mock_ai import get_mock_generate_full_response, should_mock_ai
            if should_mock_ai():
                job_id = uuid.uuid4().hex[:12]
                mock_response = get_mock_generate_full_response(prompt=prompt, job_id=job_id)
                return jsonify(mock_response)
        except ImportError:
            pass

        if model is not None:
            allowed_models = {"VIOLA-CHAT", "VIOLA-GENERATE"}
            if model not in allowed_models:
                return jsonify({"error": f"Invalid model. Allowed: {sorted(allowed_models)}"}), 400

        from utils.ai_tools.model_config import get_endpoint_chain
        if not get_endpoint_chain(heavy=True):
            return jsonify({"error": "AIOTOMASI endpoint not configured (set AIOTOMASI_API{1,2,3} + AIOTOMASI_APIKEY{1,2,3})"}), 503

        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({"error": "Unauthorized"}), 401
        job_id = uuid.uuid4().hex[:12]
        _job_create(job_id, int(user_id), prompt, paper_id=paper_id)
        threading.Thread(
            target=_run_generate_full_job,
            args=(job_id, prompt, user_id),
            kwargs={"topic": topic, "style": style, "pdf_texts": pdf_texts, "paper_id": paper_id, "conv_id": conv_id},
            daemon=True,
        ).start()
        return jsonify({"success": True, "job_id": job_id})

    except Exception as e:
        log.exception("unhandled error")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/job/<job_id>", methods=["GET"])
@jwt_required()
def get_job_status(job_id):
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    job = _job_get(job_id, user_id)
    if job is None:
        return jsonify({"error": "Job not found or already retrieved"}), 404

    elapsed = int(
        (
            datetime.now(timezone.utc)
            - (
                job.started_at.replace(tzinfo=timezone.utc)
                if job.started_at and job.started_at.tzinfo is None
                else (job.started_at or datetime.now(timezone.utc))
            )
        ).total_seconds()
    )
    if job.status == "pending":
        return jsonify({"status": "pending", "elapsed": elapsed})
    # Don't delete the row on done/error any more — the badge inbox
    # (/api/me/ai-jobs/recent) and the active-job lookup both need the row to
    # stay around. Cleanup of stale rows is handled by a future cron sweep.
    if job.status == "done":
        paper = (job.result or {}).get("partial_paper") or job.result or {}
        # Backwards-compat: legacy callers expected the full paper dict here.
        # The chunked path stores the canonical paper under partial_paper at
        # the final 'combine' checkpoint; older legacy path stored the dict
        # directly. Both shapes are tolerated.
        if isinstance(paper, dict) and "sections" not in paper and isinstance(job.result, dict):
            paper = job.result
        return jsonify(
            {"status": "done", "success": True, "paper": paper, "usage": {}, "elapsed": elapsed}
        )

    err = job.error or "Unknown error"
    timeout_flag = bool(job.timeout)
    return jsonify({"status": "error", "error": err, "timeout": timeout_flag, "elapsed": elapsed})


# ─── Topics / Styles / PDF Upload ─────────────────────────────────────────────


@app.route("/api/topics", methods=["GET"])
@jwt_required()
def list_topics():
    """Return sorted list of available topic slugs (cached)."""
    from utils.core.cache import cached

    @cached(ttl_seconds=3600)  # Cache for 1 hour
    def _get_topics():
        topic_dir = Path(__file__).parent / "tools" / "paperfull" / "prompt" / "topic"
        return sorted(p.stem for p in topic_dir.glob("*.txt") if not p.stem.startswith("_"))

    topics = _get_topics()
    return jsonify({"topics": topics})


@app.route("/api/styles", methods=["GET"])
@jwt_required()
def list_styles():
    """Return sorted list of available citation style slugs (cached)."""
    from utils.core.cache import cached

    @cached(ttl_seconds=3600)  # Cache for 1 hour
    def _get_styles():
        style_dir = Path(__file__).parent / "tools" / "paperfull" / "prompt" / "style"
        return sorted(p.stem for p in style_dir.glob("*.txt"))

    styles = _get_styles()
    return jsonify({"styles": styles})


MAX_PDF_FILES = 50
MAX_WORDS_PER_FILE = 0  # No limit — all text is included (was 5000)


@app.route("/api/upload-pdfs", methods=["POST"])
@limiter.limit("20 per minute")
@jwt_required()
def upload_pdfs():
    """Extract text from up to 5 uploaded PDF/DOCX files (max 5000 words each).

    Routes through the shared 20-worker extraction pool in files_bp so a chat
    upload doesn't block a Files-tab upload (and vice versa).
    """
    import io  # noqa: PLC0415

    from docx import Document  # noqa: PLC0415
    # _EXTRACT_POOL imported at top from tools.File

    from tools.File.extract_pdfs import extract_text_from_pdf  # noqa: PLC0415

    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "No files uploaded"}), 400
    if len(files) > MAX_PDF_FILES:
        return jsonify({"error": f"Max {MAX_PDF_FILES} files allowed"}), 400

    # Read bytes synchronously (cheap), then extract in parallel.
    payloads = []
    warnings = []
    MAX_PDF_SIZE = 100 * 1024 * 1024  # 100MB per file — user requested
    for f in files:
        filename = (f.filename or "").lower()
        try:
            # BUG FIX: Add size check before reading entire file
            f.stream.seek(0, 2)
            size = f.stream.tell()
            f.stream.seek(0)
            if size > MAX_PDF_SIZE:
                warnings.append(f"{f.filename}: file terlalu besar (max 100MB)")
                continue
            if size == 0:
                warnings.append(f"{f.filename}: file kosong")
                continue
            data = f.stream.read()
        except Exception as e:
            warnings.append(f"{f.filename}: gagal baca stream ({e})")
            continue
        if filename.endswith(".pdf"):
            payloads.append(("pdf", f.filename, data))
        elif filename.endswith(".docx"):
            payloads.append(("docx", f.filename, data))
        elif filename.endswith(".doc"):
            payloads.append(("doc_legacy", f.filename, data))
        elif filename.endswith(".txt"):
            payloads.append(("txt", f.filename, data))
        elif filename.endswith(".md"):
            payloads.append(("md", f.filename, data))
        else:
            warnings.append(f"{f.filename}: format tidak didukung (PDF, DOCX, TXT, MD saja)")

    def _extract(kind, name, blob):
        try:
            if kind == "pdf":
                return extract_text_from_pdf(io.BytesIO(blob))
            if kind == "txt" or kind == "md":
                try:
                    return blob.decode("utf-8")
                except UnicodeDecodeError:
                    return blob.decode("latin-1", errors="replace")
            if kind == "doc_legacy":
                # Convert .doc → .docx via LibreOffice, then extract text
                import tempfile, subprocess  # noqa: PLC0415
                with tempfile.TemporaryDirectory() as tmpdir:
                    doc_path = os.path.join(tmpdir, name)
                    with open(doc_path, "wb") as fh:
                        fh.write(blob)
                    subprocess.run(
                        ["libreoffice", "--headless", "--convert-to", "docx", "--outdir", tmpdir, doc_path],
                        capture_output=True, timeout=60,
                    )
                    conv_name = name.rsplit(".", 1)[0] + ".docx"
                    conv_path = os.path.join(tmpdir, conv_name)
                    if os.path.exists(conv_path):
                        with open(conv_path, "rb") as fh:
                            doc = Document(fh)
                    else:
                        return f"[Error converting {name}: output docx not found]"
            else:
                doc = Document(io.BytesIO(blob))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception as e:
            return f"[Error reading {name}: {e}]"

    futures = [
        (name, _EXTRACT_POOL.submit(_extract, kind, name, blob)) for kind, name, blob in payloads
    ]

    results = []
    for name, fut in futures:
        try:
            text = fut.result(timeout=120)
        except Exception as e:
            warnings.append(f"{name}: gagal mengekstrak ({e})")
            continue
        if MAX_WORDS_PER_FILE > 0:
            words = text.split()
            if len(words) > MAX_WORDS_PER_FILE:
                warnings.append(f"{name}: file terlalu besar, dibatasi ke {MAX_WORDS_PER_FILE} kata")
                text = " ".join(words[:MAX_WORDS_PER_FILE])
        results.append(text)

    return jsonify({"pdf_texts": results, "warnings": warnings})


# ─── Paper Files (PDF/DOCX/DOC/TXT/MD) ────────────────────────────────────
# Moved to files_bp.py — registered above.

# ─── Paper-specific Image Upload + signed URLs + image serving ───────────
# Moved to images_bp.py — registered above (paper_images_bp + image_serve_bp).

_PAPER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_FILENAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


@app.route("/api/journals", methods=["GET"])
@jwt_required()
def list_journals():
    try:
        return jsonify({"journals": _available_journals()})
    except Exception as e:
        return jsonify({"error": "Internal server error"}), 500


_MDPI_JOURNALS_CACHE = None

def _mdpi_journals():
    """Return MDPI sub-journal metadata from journals.json (cached)."""
    global _MDPI_JOURNALS_CACHE
    if _MDPI_JOURNALS_CACHE is not None:
        return _MDPI_JOURNALS_CACHE
    journals_path = TEMPLATE_FOLDER / "journals.json"
    if not journals_path.exists():
        _MDPI_JOURNALS_CACHE = []
        return []
    import json as _json
    data = _json.loads(journals_path.read_text(encoding="utf-8"))
    _MDPI_JOURNALS_CACHE = [
        {
            "key": v.get("key", k),
            "short_name": v.get("short_name", k),
            "year": v.get("year", 2025),
            "volume": v.get("volume", 1),
        }
        for k, v in data.items()
    ]
    # Sort by short_name
    _MDPI_JOURNALS_CACHE.sort(key=lambda j: j["short_name"].lower())
    return _MDPI_JOURNALS_CACHE


@app.route("/api/journals/mdpi", methods=["GET"])
@jwt_required()
def list_mdpi_journals():
    try:
        return jsonify({"mdpi_journals": _mdpi_journals()})
    except Exception as e:
        return jsonify({"error": "Internal server error"}), 500


# ─── Legacy Image Upload ──────────────────────────────────────────────────────


def _is_image_bytes(head: bytes, ext: str) -> bool:
    """Validate image file by magic bytes."""
    if not head:
        return False
    if ext in ('.png',) and head[:8] == b'\x89PNG\r\n\x1a\n':
        return True
    if ext in ('.jpg', '.jpeg') and head[:2] == b'\xff\xd8':
        return True
    if ext in ('.gif',) and head[:6] in (b'GIF87a', b'GIF89a'):
        return True
    if ext in ('.bmp',) and head[:2] == b'BM':
        return True
    if ext in ('.webp',) and head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return True
    return False


@app.route("/api/upload-image", methods=["POST"])
@limiter.limit("30 per minute")
@jwt_required()
def upload_image_legacy():
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400
        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No file selected"}), 400
        ext = Path(file.filename).suffix.lower()
        allowed_image_exts = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
        if ext not in allowed_image_exts:
            return jsonify({"error": "Invalid image format"}), 400
        # BUG FIX: Add size check before processing
        file.stream.seek(0, 2)
        size = file.stream.tell()
        file.stream.seek(0)
        if size > 10 * 1024 * 1024:
            return jsonify({"error": "Image too large (max 10MB)"}), 400
        head = file.stream.read(16)
        file.stream.seek(0)
        if not _is_image_bytes(head, ext):
            return jsonify({"error": "Invalid image file"}), 400
        # Per-user uploads dir for legacy endpoint
        user_id = int(get_jwt_identity())
        user_upload_dir = _get_user_dir(user_id, "uploads") / "legacy"
        user_upload_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4().hex}{ext}"
        filepath = user_upload_dir / filename
        file.save(str(filepath))
        return jsonify(
            {
                "success": True,
                "filename": filename,
                "url": f"/api/images/legacy/{filename}",
                "originalName": file.filename[:255],
            }
        )
    except Exception as e:
        log.exception("unhandled error")
        return jsonify({"error": "Internal server error"}), 500


# ─── Export DOCX ──────────────────────────────────────────────────────────────


@app.route("/api/export", methods=["POST"])
@limiter.limit("20 per minute")
@jwt_required()
def export_docx():
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "No paper data provided"}), 400
        paper = data.get("paper", data)

        # If paper_id provided, always verify ownership — even if body contains paper data
        paper_id = data.get("paper_id") or (paper.get("id") if isinstance(paper, dict) else None)
        if paper_id:
            from utils.database.models import Paper
            user_id = int(get_jwt_identity())
            db_paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
            if not db_paper:
                return jsonify({"error": "Paper not found or access denied"}), 404
            # If body has no figure data, use DB version
            if not isinstance(paper, dict) or "figures" not in paper:
                if db_paper.data:
                    paper = db_paper.data
                log.info("[export] Loaded paper %s from DB, %d figures", paper_id, len(paper.get("figures", [])))

        journal_raw = data.get("journal")
        if isinstance(paper, dict) and not journal_raw:
            journal_raw = paper.get("journal")
        journal_code = _resolve_journal_code(journal_raw)
        try:
            canonical_journal, builder, pdf_builder = _get_builder_for_journal(journal_code)
        except Exception as e:
            log.exception("journal builder error")
            return jsonify({"error": "Internal server error", "available": _available_journals()}), 400

        # Wire any completed image-generation jobs into the paper's figure
        # Path fields so the exporter embeds real images instead of falling
        # back to the raw prompt text. Best-effort: never block export.
        try:
            if isinstance(paper, dict):
                _pid = str(paper.get("id") or data.get("paper_id") or "").strip()
                # Fallback: dig into paper_data wrapper for paper_id
                if not _pid and isinstance(paper.get("paper_data"), dict):
                    _pid = str(paper["paper_data"].get("paper_id", "")).strip()
                if _pid:
                    from tools.image_generation.reconcile import reconcile_figure_images
                    from sqlalchemy.orm.attributes import flag_modified
                    _user_upload_dir = _get_user_dir(int(get_jwt_identity()), "uploads")
                    reconcile_figure_images(_pid, paper, _user_upload_dir)

                    # Also reconcile section images (handles inline gambar items)
                    from tools.paperfull.jobs import _reconcile_section_images
                    _reconcile_section_images(paper, _pid, _user_upload_dir)

                    # Persist the reconciled paths back to the database
                    try:
                        db_paper = Paper.query.filter_by(id=_pid, user_id=int(get_jwt_identity())).first()
                        if db_paper:
                            db_paper.data = paper
                            flag_modified(db_paper, "data")
                            safe_commit()
                    except Exception as persist_err:
                        log.warning("[export] Failed to persist reconciled paths to DB: %s", persist_err)
        except Exception:
            log.warning("figure image reconciliation failed", exc_info=True)

        # Normalize paper structure: distribute figures array into sections
        # as inline items so generators that read section.content can find them.
        try:
            if isinstance(paper, dict):
                _distribute_figures_to_sections(paper)
        except Exception:
            log.warning("figure distribution to sections failed", exc_info=True)

        # Inject a formatted ``text`` into structured reference dicts so every
        # journal generator (most read ref["text"]) renders citations instead
        # of skipping structured-only references. Style matches the journal.
        try:
            if isinstance(paper, dict):
                from tools.preview.ref_normalize import normalize_references, style_for_journal
                normalize_references(paper, style=style_for_journal(canonical_journal))
        except Exception:
            log.warning("reference normalization failed", exc_info=True)

        # Normalize formula LaTeX: fix AI-generated content with missing
        # backslashes (e.g. "beginbmatrix" → "\begin{bmatrix}") and remove
        # empty formula items that would otherwise be silently dropped by
        # generators (causing "Formula Missing" checker penalties).
        try:
            if isinstance(paper, dict):
                _normalize_formulas(paper)
        except Exception:
            log.warning("formula normalization failed", exc_info=True)

        # Strip [N] prefix from reference text to avoid double numbering
        # when generators add their own [i] prefix on top.
        try:
            if isinstance(paper, dict):
                _strip_ref_numbering(paper)
        except Exception:
            log.warning("reference numbering strip failed", exc_info=True)

        # Get user info for per-user export path
        user_id = get_jwt_identity()
        try:
            from utils.core.user_storage import get_username
            username = get_username(user_id=user_id)
        except Exception:
            username = f"user_{user_id}"

        # Use per-user export path: user/<username>/<paper_id>/
        paper_id = str(paper.get("id") or data.get("paper_id") or "unknown")
        if not _PAPER_ID_RE.match(paper_id):
            return jsonify({"error": "Invalid paper_id format"}), 400
        paper_dir = _user_paper_dir(user_id, paper_id)
        
        json_filename = f"_tmp_{uuid.uuid4().hex[:8]}.json"
        json_filepath = paper_dir / json_filename
        json_filepath.write_text(json.dumps(paper, ensure_ascii=False, indent=2), encoding="utf-8")
        output_path = None
        _export_ok = False
        try:
            # Save DOCX to user/paper/ with normalized naming (1 DOCX per paper)
            paper_title = paper.get("title", "paper")
            output_path = _paper_file_path(paper_id, paper_title, canonical_journal, "docx", user_id=user_id)
            builder(json_filepath, output_path)

            # Also generate PDF alongside DOCX (1 PDF per paper)
            try:
                pdf_dest = _paper_file_path(paper_id, paper_title, canonical_journal, "pdf", user_id=user_id)
                if callable(pdf_builder):
                    pdf_builder(json_path=json_filepath, pdf_path=pdf_dest)
                else:
                    _run_libreoffice_pdf(output_path, pdf_dest)
                log.info("[export] PDF generated: %s", pdf_dest)
            except Exception:
                log.warning("[export] PDF generation failed (DOCX exported OK)", exc_info=True)

            try:
                from utils.core.user_storage import update_judul_paper_by_id
                judul = data.get("title", paper.get("title", "untitled"))
                update_judul_paper_by_id(paper_id, paper_title, canonical_journal, data)
            except Exception:
                log.warning("Gagal simpan ke user storage", exc_info=True)

            safe_title = re.sub(r"[^a-zA-Z0-9_\-]+", "_", str(paper.get("title", "paper"))).strip(
                "_"
            )
            if not safe_title:
                safe_title = "paper"
            download_name = f"{canonical_journal}_{safe_title[:60]}.docx"
            response = send_file(
                str(output_path),
                as_attachment=True,
                download_name=download_name,
                mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

            _export_ok = True
            return response
        finally:
            # Don't delete output_path — it's in user/paper/ and stays
            if not _export_ok:
                try:
                    if output_path is not None:
                        output_path.unlink(missing_ok=True)
                except Exception as _e:
                    log.warning("Partial cleanup unlink failed for %s: %s", output_path, _e)
            json_filepath.unlink(missing_ok=True)
    except Exception as e:
        log.exception("unhandled error")
        return jsonify({"error": "Internal server error"}), 500


# ─── PDF Preview ──────────────────────────────────────────────────────────────

def _user_paper_dir(user_id: int, paper_id: str = None) -> Path:
    """Return ``user/<username>/<paper_id>/`` (or just ``user/<username>/`` if no paper_id).
    
    Falls back to ``user/<paper_id>/`` when username lookup fails.
    """
    try:
        from utils.core.user_storage import get_username
        username = get_username(user_id=user_id)
    except Exception:
        username = f"user_{user_id}"
    safe_user = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(username)).strip("_") or "anonymous"
    path = USER_BASE / safe_user
    if paper_id:
        path = path / paper_id
    path.mkdir(parents=True, exist_ok=True)
    return path

def _paper_file_path(paper_id, paper_title: str, journal_code: str, ext: str, *, cleanup_old: bool = True, user_id: int = None) -> Path:
    """Return ``user/<username>/<paper_id>/<safe_title>_<journal>.<ext>``.

    All artifacts for a paper live under ``user/<username>/<paper_id>/``.
    Same title+journal combination overwrites existing file.
    When title or journal changes, old files of the same extension are removed.
    Falls back to ``user/<paper_id>/`` if user_id not provided (legacy compat).
    """
    safe_title = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(paper_title or "paper")).strip("_")[:60].rstrip("_")
    if not safe_title:
        safe_title = "paper"
    safe_journal = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(journal_code or "journal")).strip("_") or "journal"
    safe_name = f"{safe_title}_{safe_journal}"
    safe_paper_id = str(paper_id)
    if not _PAPER_ID_RE.match(safe_paper_id):
        raise ValueError(f"Invalid paper_id: {safe_paper_id}")
    if user_id is not None:
        paper_dir = _user_paper_dir(user_id, safe_paper_id)
    else:
        # Legacy fallback: user/<paper_id>/
        paper_dir = USER_BASE / safe_paper_id
        paper_dir.mkdir(parents=True, exist_ok=True)
    target = paper_dir / f"{safe_name}.{ext}"
    if cleanup_old:
        for old in paper_dir.glob(f"*.{ext}"):
            if old != target:
                try:
                    old.unlink()
                except Exception:
                    pass
    return target

def _pdf_preview_path(user_id: int, paper_id: str) -> Path:
    """Legacy fallback redirected to canonical paper folder."""
    return _paper_file_path(paper_id, "paper", "preview", "pdf", cleanup_old=False, user_id=user_id)

def _run_libreoffice_pdf(source_path: Path, output_path: Path) -> None:
    output_dir = output_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            ["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(output_dir), str(source_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )
    except subprocess.TimeoutExpired as e:
        # Kill any orphaned soffice processes for this file
        try:
            subprocess.run(["pkill", "-f", str(source_path)], timeout=5)
        except Exception:
            pass
        raise RuntimeError(f"LibreOffice PDF conversion timed out (120s): {source_path.name}")

    expected_pdf = output_dir / (source_path.stem + ".pdf")

    # soffice may return non-zero with harmless javaldx warning — check for PDF first
    if expected_pdf.exists() and expected_pdf.stat().st_size > 0:
        if expected_pdf != output_path:
            if output_path.exists():
                output_path.unlink()
            expected_pdf.replace(output_path)
        return

    if result.returncode != 0:
        raise RuntimeError(
            f"LibreOffice PDF conversion failed: {result.stderr.decode('utf-8', errors='ignore')}"
        )
    if expected_pdf != output_path:
        if output_path.exists():
            output_path.unlink()
        expected_pdf.replace(output_path)


def _pdf_preview_render(user_id: int, paper_id: str, journal_code: str, paper_json_path: Path) -> str | None:
    try:
        canonical, builder, pdf_builder = _get_builder_for_journal(_resolve_journal_code(journal_code))
    except Exception:
        log.exception("[preview-pdf] journal builder error")
        return None

    # Load paper data, unwrap paper_data.paper → flat for generator
    try:
        _paper_data = json.loads(paper_json_path.read_text(encoding="utf-8"))
        _title = _paper_data.get("title") or _paper_data.get("paper_data", {}).get("paper", {}).get("title") or ""
    except Exception:
        _title = ""

    # Unwrap paper_data.paper so generators see section1..N at top level
    # (same logic as _make_generate_adapter)
    if isinstance(_paper_data, dict) and "paper_data" in _paper_data:
        pd = _paper_data["paper_data"]
        _unwrapped = pd.get("paper", pd) if isinstance(pd, dict) else _paper_data
        if isinstance(_unwrapped, dict) and isinstance(pd, dict):
            for key in ("figures", "tables", "equations"):
                if key in pd and key not in _unwrapped:
                    _unwrapped[key] = pd[key]
        if isinstance(_unwrapped, dict) and "figures" in _unwrapped:
            _distribute_figures_to_sections(_unwrapped)
        paper_json_path.write_text(json.dumps(_unwrapped, ensure_ascii=False, indent=2), encoding="utf-8")

    pdf_path = _paper_file_path(paper_id, _title, journal_code, "pdf", user_id=user_id)
    docx_path = _paper_file_path(paper_id, _title, journal_code, "docx", user_id=user_id)
    try:
        if callable(pdf_builder):
            # Use the gen's own build_pdf (direct docx→pdf pipeline)
            pdf_builder(json_path=paper_json_path, pdf_path=pdf_path)
            # Also save DOCX via build_document for download
            try:
                builder(paper_json_path, docx_path)
            except Exception:
                log.warning("[preview-pdf] failed to save DOCX alongside PDF", exc_info=True)
        else:
            # Fallback: build_document → LibreOffice
            builder(paper_json_path, docx_path)
            _run_libreoffice_pdf(docx_path, pdf_path)
        return str(pdf_path)
    except Exception:
        log.exception("[preview-pdf] render error")
        return None


@app.route("/api/papers/<paper_id>/pdf-preview", methods=["POST"])
@limiter.limit("100 per minute")
@jwt_required()
def paper_pdf_preview(paper_id: str):
    log.info("[preview-pdf] POST received, paper_id=%s", paper_id)
    try:
        data = request.get_json(silent=True) or {}
        paper = data.get("paper", data)

        user_id = int(get_jwt_identity())

        # If paper data not provided, load from DB
        if not isinstance(paper, dict) or not paper.get("title"):
            from utils.database.models import Paper
            db_paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
            if not db_paper:
                return jsonify({"error": "Paper not found"}), 404
            if db_paper.data:
                paper = db_paper.data

        if not isinstance(paper, dict):
            return jsonify({"error": "No paper data provided"}), 400

        # Unwrap paper_data.paper so normalizations + generators see flat structure
        if "paper_data" in paper:
            pd = paper["paper_data"]
            if isinstance(pd, dict):
                paper = pd.get("paper", pd)
                # Inject figures/tables from wrapper level
                for key in ("figures", "tables", "equations"):
                    if key in pd and key not in paper:
                        paper[key] = pd[key]

        journal_raw = data.get("journal") or paper.get("journal")
        journal_code = _resolve_journal_code(journal_raw)

        # Reuse same normalization as export so preview matches exported docx
        try:
            _pid = str(paper.get("id") or paper_id or "").strip()
            if _pid and user_id:
                _user_upload_dir = _get_user_dir(int(user_id), "uploads")
                from tools.image_generation.reconcile import reconcile_figure_images
                from tools.paperfull.jobs import _reconcile_section_images
                reconcile_figure_images(_pid, paper, _user_upload_dir)
                _reconcile_section_images(paper, _pid, _user_upload_dir)
        except Exception:
            log.warning("preview pdf figure reconcile failed", exc_info=True)

        try:
            if isinstance(paper, dict):
                _distribute_figures_to_sections(paper)
        except Exception:
            log.warning("preview pdf figure distribution failed", exc_info=True)

        try:
            if isinstance(paper, dict):
                from tools.preview.ref_normalize import normalize_references, style_for_journal
                normalize_references(paper, style=style_for_journal(_resolve_journal_code(journal_raw)))
        except Exception:
            log.warning("preview pdf reference normalize failed", exc_info=True)

        try:
            if isinstance(paper, dict):
                _normalize_formulas(paper)
        except Exception:
            log.warning("preview pdf formula normalize failed", exc_info=True)

        try:
            if isinstance(paper, dict):
                _strip_ref_numbering(paper)
        except Exception:
            log.warning("preview pdf ref numbering failed", exc_info=True)

        json_filename = f"_tmp_{uuid.uuid4().hex[:8]}.json"
        if not _PAPER_ID_RE.match(paper_id):
            return jsonify({"error": "Invalid paper_id format"}), 400
        paper_dir = _user_paper_dir(user_id, paper_id)
        json_filepath = paper_dir / json_filename
        try:
            json_filepath.write_text(json.dumps(paper, ensure_ascii=False, indent=2), encoding="utf-8")
            pdf_path = _pdf_preview_render(user_id, paper_id, journal_code, json_filepath)
            if not pdf_path:
                return jsonify({"error": "Failed to render PDF preview"}), 500
            # Build URL with query params so serve endpoint can find the right file
            safe_title = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(paper.get("title", "paper")).strip("_"))[:60]
            from urllib.parse import urlencode
            qs = urlencode({"journal": journal_code, "title": safe_title})
            return jsonify({"pdf_url": f"/api/papers/{paper_id}/preview.pdf?{qs}", "journal": journal_code})
        finally:
            try:
                json_filepath.unlink(missing_ok=True)
            except Exception:
                pass
    except Exception as e:
        log.exception("unhandled preview pdf error: %s", e)
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/papers/<paper_id>/preview.pdf", methods=["GET", "OPTIONS"])
@app.route("/api/papers/<paper_id>/preview.docx", methods=["GET", "OPTIONS"])
@limiter.exempt
def serve_paper_pdf_preview(paper_id: str):
    """Serve the generated PDF/DOCX for a paper.

    Called from:
    - api.get(url) in the frontend (Authorization header sent by axios)
    - <iframe> in the same page (cookies or no auth)

    Authorization: possession of the URL is sufficient proof. We still
    validate paper_id format to prevent path traversal.
    """
    from flask import request as flask_request

    # 👮 Prevent path traversal via malformed paper_id
    if not _PAPER_ID_RE.match(paper_id):
        return jsonify({"error": "Invalid paper_id"}), 400

    is_docx = flask_request.path.endswith(".docx")
    ext = "docx" if is_docx else "pdf"

    journal_code = flask_request.args.get("journal", "")
    title = flask_request.args.get("title", "")

    # Let _paper_file_path handle ALL sanitization to avoid filename mismatches.
    # Previously this did its own regex (keeping \s, 120-char limit) which diverged
    # from _paper_file_path's regex (no \s, 60-char limit, strip("_")).
    file_path = None

    if journal_code:
        # Primary: canonical paper_dir path (_paper_file_path sanitizes internally)
        from utils.database.models import Paper
        paper = Paper.query.filter_by(id=paper_id).first()
        if paper:
            file_path = _paper_file_path(paper_id, title or "paper", journal_code, ext, cleanup_old=False, user_id=paper.user_id)
            if not file_path.exists():
                file_path = None

    if file_path is None or not file_path.exists():
        # Legacy fallback: user/<paper_id>/ (old path before per-user fix)
        legacy_candidate = _paper_file_path(paper_id, title or "paper", journal_code or "journal", ext, cleanup_old=False)
        if legacy_candidate.exists():
            file_path = legacy_candidate
        else:
            file_path = None

    if file_path is None or not file_path.exists():
        # Legacy fallback: user/papers/<paper_id>/paper.pdf
        from utils.database.models import Paper
        paper = Paper.query.filter_by(id=paper_id).first()
        if paper:
            file_path = _pdf_preview_path(paper.user_id, paper_id)
            if ext == "docx":
                file_path = file_path.with_suffix(".docx")

    if file_path is None or not file_path.exists():
        return jsonify({"error": "Preview not ready"}), 404

    # 🛡️ Final containment check: file must be under USER_BASE
    try:
        resolved = file_path.resolve()
        resolved.relative_to(USER_BASE.resolve())
    except ValueError:
        log.warning("path traversal blocked for paper_id=%s path=%s", paper_id, file_path)
        return jsonify({"error": "Invalid path"}), 403

    response = send_file(
        str(file_path),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document" if is_docx else "application/pdf",
        as_attachment=False,
        download_name=f"{paper_id}.{ext}",
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Access-Control-Allow-Origin"] = request.origin or "*"
    return response



# ─── Paper CRUD ───────────────────────────────────────────────────────────────
# Moved to papers_bp.py — registered above. Keeping this header as a breadcrumb.

# ─── Word Add-on ─────────────────────────────────────────────────────────────

WORD_ADDON_DIR = Path(__file__).parent / "tools" / "word_addon"


_WORD_ADDON_ORIGINS_RAW = os.getenv("WORD_ADDON_CORS_ORIGINS", "http://localhost:1000,http://localhost:5173,http://localhost:3001,http://localhost:8000")
_WORD_ADDON_ORIGINS = {o.strip() for o in _WORD_ADDON_ORIGINS_RAW.split(",") if o.strip()}


def _office_cors(resp):
    """Add CORS headers required by Office.js add-in runtime."""
    origin = request.headers.get("Origin", "")
    if origin in _WORD_ADDON_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-CSRF-TOKEN"
    resp.headers["Access-Control-Allow-Credentials"] = "true"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@limiter.exempt
@app.route("/api/word-addon/manifest.xml", methods=["GET", "OPTIONS"])
def word_addon_manifest():
    """Serve add-in manifest for sideloading into Word."""
    if request.method == "OPTIONS":
        return _office_cors(Response())
    manifest_path = WORD_ADDON_DIR / "manifest.xml"
    if not manifest_path.is_file():
        return jsonify({"error": "Manifest not found"}), 404
    manifest_content = manifest_path.read_text(encoding="utf-8").replace("{BASE_URL}", _APP_BASE_URL)
    return _office_cors(Response(manifest_content, mimetype="application/xml"))


@limiter.exempt
@app.route("/api/word-addon/download-manifest", methods=["GET", "OPTIONS"])
def word_addon_download_manifest():
    """Force download manifest.xml for Word Add-in installation."""
    if request.method == "OPTIONS":
        return _office_cors(Response())
    manifest_path = WORD_ADDON_DIR / "manifest.xml"
    if not manifest_path.is_file():
        return jsonify({"error": "Manifest not found"}), 404
    manifest_content = manifest_path.read_text(encoding="utf-8").replace("{BASE_URL}", _APP_BASE_URL)
    resp = Response(manifest_content, mimetype="application/xml")
    resp.headers["Content-Disposition"] = 'attachment; filename="VIOLA-AI-Assistant.xml"'
    return _office_cors(resp)


@limiter.exempt
@app.route("/api/word-addon/<path:filepath>", methods=["GET", "OPTIONS"])
def word_addon_static(filepath):
    """Serve add-in static files from word_addon/ directory (supports subdirectories)."""
    if request.method == "OPTIONS":
        return _office_cors(Response())

    try:
        safe_path = (WORD_ADDON_DIR / filepath).resolve()
        if not str(safe_path).startswith(str(WORD_ADDON_DIR.resolve())):
            return jsonify({"error": "Invalid path"}), 403
    except ValueError:
        return jsonify({"error": "Invalid path"}), 403

    allowed_extensions = {'.html', '.js', '.css', '.png', '.json'}
    if safe_path.suffix not in allowed_extensions:
        return jsonify({"error": "File type not allowed"}), 403

    if not safe_path.is_file():
        return jsonify({"error": "File not found"}), 404

    mime_map = {
        ".html": "text/html",
        ".js": "application/javascript",
        ".css": "text/css",
        ".png": "image/png",
        ".json": "application/json",
    }
    mimetype = mime_map.get(safe_path.suffix, "application/octet-stream")
    return _office_cors(send_file(str(safe_path), mimetype=mimetype))


@app.route("/api/word-addon/extract", methods=["POST", "OPTIONS"])
@limiter.limit("100 per minute")  # rate limit for this endpoint
@jwt_required()
def word_addon_extract():
    """Extract text from uploaded PDF, DOCX, or TXT file."""
    if request.method == "OPTIONS":
        return _office_cors(jsonify({}))
    import io  # noqa: PLC0415
    from docx import Document  # noqa: PLC0415
    from tools.File.extract_pdfs import extract_text_from_pdf  # noqa: PLC0415

    if "file" not in request.files:
        return _office_cors(jsonify({"error": "No file uploaded"})), 400
    file = request.files["file"]
    if not file.filename:
        return _office_cors(jsonify({"error": "No file selected"})), 400
    filename = file.filename.lower()
    try:
        # Check file size BEFORE reading to prevent OOM on huge uploads
        file.stream.seek(0, 2)  # Seek to end
        file_size = file.stream.tell()
        file.stream.seek(0)  # Reset to beginning
        if file_size > 100 * 1024 * 1024:
            return _office_cors(jsonify({"error": "File too large (max 100MB)"})), 413
        data = file.read()
        if len(data) > 100 * 1024 * 1024:
            return _office_cors(jsonify({"error": "File too large (max 100MB)"})), 413
        if filename.endswith(".pdf"):
            text = extract_text_from_pdf(io.BytesIO(data))
        elif filename.endswith(".docx"):
            doc = Document(io.BytesIO(data))
            text = "\n".join(p.text for p in doc.paragraphs)
        elif filename.endswith(".doc"):
            # Convert .doc → .docx via LibreOffice
            import tempfile, subprocess  # noqa: PLC0415
            name = file.filename
            with tempfile.TemporaryDirectory() as tmpdir:
                doc_path = os.path.join(tmpdir, name)
                with open(doc_path, "wb") as fh:
                    fh.write(data)
                subprocess.run(
                    ["libreoffice", "--headless", "--convert-to", "docx", "--outdir", tmpdir, doc_path],
                    capture_output=True, timeout=60,
                )
                conv_name = name.rsplit(".", 1)[0] + ".docx"
                conv_path = os.path.join(tmpdir, conv_name)
                if os.path.exists(conv_path):
                    with open(conv_path, "rb") as fh:
                        doc = Document(fh)
                        text = "\n".join(p.text for p in doc.paragraphs)
                else:
                    return _office_cors(jsonify({"error": f"Failed to convert {name}"})), 500
        elif filename.endswith(".txt"):
            text = data.decode("utf-8", errors="replace")
        else:
            return _office_cors(jsonify({"error": "Unsupported format (PDF, DOCX, TXT only)"})), 400
        max_words = 5000
        words = text.split()
        if len(words) > max_words:
            words = words[:max_words]
            text = " ".join(words)
        return _office_cors(jsonify({"text": text}))
    except Exception as e:
        log.exception("office extraction failed")
        return _office_cors(jsonify({"error": "Internal server error"})), 500


_INSTALL_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>PaperFull — Install Word Add-in</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: "Segoe UI", system-ui, sans-serif; background: #f0f4f8; color: #333; display: flex; justify-content: center; align-items: center; min-height: 100vh; padding: 20px; }
    .card { background: #fff; border-radius: 12px; box-shadow: 0 4px 24px rgba(0,0,0,.08); padding: 36px 40px; max-width: 600px; width: 100%; }
    h1 { font-size: 24px; font-weight: 700; margin-bottom: 4px; }
    .subtitle { color: #666; margin-bottom: 24px; font-size: 14px; }
    h2 { font-size: 15px; font-weight: 600; margin: 24px 0 8px; color: #1a73e8; }
    ol, ul { padding-left: 20px; line-height: 1.8; }
    li { font-size: 14px; }
    code { background: #f1f3f5; padding: 2px 6px; border-radius: 3px; font-size: 12px; word-break: break-all; }
    .btn { display: block; width: 100%; padding: 12px; border: none; border-radius: 6px; font-size: 15px; font-weight: 600; cursor: pointer; text-align: center; text-decoration: none; margin-top: 12px; }
    .btn-primary { background: #1a73e8; color: #fff; }
    .btn-primary:hover { background: #1557b0; }
    .btn-secondary { background: #e8f0fe; color: #1a73e8; }
    .btn-secondary:hover { background: #d2e3fc; }
    .btn-success { background: #0f9d58; color: #fff; }
    .btn-success:hover { background: #0b8043; }
    .btn-outline { background: transparent; color: #1a73e8; border: 1px solid #1a73e8; }
    .btn-outline:hover { background: #e8f0fe; }
    .btn-row { display: flex; gap: 8px; margin-top: 12px; }
    .btn-row .btn { margin-top: 0; }
    .btn-half { flex: 1; }
    .note { margin-top: 16px; font-size: 12px; color: #888; line-height: 1.5; }
    .divider { border: none; border-top: 1px solid #e0e0e0; margin: 24px 0; }
    .badge { display: inline-block; background: #e8f0fe; color: #1a73e8; font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 10px; margin-left: 6px; }
    .step-icon { display: inline-block; width: 22px; height: 22px; background: #1a73e8; color: #fff; border-radius: 50%; text-align: center; line-height: 22px; font-size: 12px; font-weight: 700; margin-right: 8px; flex-shrink: 0; }
    .step { display: flex; align-items: flex-start; margin-bottom: 8px; }
    .step-content { flex: 1; font-size: 14px; line-height: 1.6; }
    #copy-toast { display: none; position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); background: #333; color: #fff; padding: 10px 20px; border-radius: 6px; font-size: 13px; z-index: 1000; }
  </style>
</head>
<body>
  <div class="card">
    <h1>PaperFull for Word</h1>
    <p class="subtitle">Install the PaperFull add-in for Microsoft Word</p>

    <h2>Word Desktop (2019 / Microsoft 365)</h2>
    <div class="step">
      <span class="step-icon">1</span>
      <span class="step-content">Download the <strong>manifest.xml</strong> file using the button below.</span>
    </div>
    <div class="step">
      <span class="step-icon">2</span>
      <span class="step-content">Open Word → <strong>Insert</strong> tab → <strong>Add-ins</strong> → <strong>My Add-ins</strong>.</span>
    </div>
    <div class="step">
      <span class="step-icon">3</span>
      <span class="step-content">Click <strong>Upload My Add-in</strong>, select the downloaded <code>manifest.xml</code>.</span>
    </div>
    <div class="step">
      <span class="step-icon">4</span>
      <span class="step-content">The PaperFull taskpane opens in the <strong>Home</strong> tab ribbon.</span>
    </div>
    <a class="btn btn-primary" href="/api/word-addon/manifest.xml" download>Download manifest.xml</a>

    <hr class="divider" />

    <h2>Word for the web <span class="badge">Quick Install</span></h2>
    <p style="font-size:13px;color:#666;margin-bottom:8px;">
      Open a document in Word for the web, then click the button below to sideload the add-in.
    </p>
    <a id="install-link" class="btn btn-success" href="#" target="_blank">
      Install to Word for the web
    </a>

    <hr class="divider" />

    <h2>Need the URL?</h2>
    <p style="font-size:13px;color:#666;margin-bottom:8px;">
      Copy the manifest URL for use with <strong>Office Admin Center</strong> or centralized deployment.
    </p>
    <div class="btn-row">
      <button id="copy-btn" class="btn btn-outline btn-half">Copy Manifest URL</button>
      <button id="open-btn" class="btn btn-outline btn-half">Open Manifest</button>
    </div>

    <p class="note">
      Requirements: Word 2019 or later, Word for Microsoft 365, or Word for the web.
      An active PaperFull account is required.
    </p>
  </div>

  <div id="copy-toast">Copied to clipboard!</div>

  <script>
    (function() {
      var manifestUrl = window.location.origin + "/api/word-addon/manifest.xml";

      var installLink = document.getElementById("install-link");
      installLink.href = "https://office.live.com/start/Word.aspx?omkt=en-US&ui=en-US&installaddin=" + encodeURIComponent(manifestUrl);

      var copyBtn = document.getElementById("copy-btn");
      copyBtn.addEventListener("click", function() {
        navigator.clipboard.writeText(manifestUrl).then(function() {
          var toast = document.getElementById("copy-toast");
          toast.style.display = "block";
          setTimeout(function() { toast.style.display = "none"; }, 2000);
        });
      });

      var openBtn = document.getElementById("open-btn");
      openBtn.addEventListener("click", function() {
        window.open(manifestUrl, "_blank");
      });
    })();
  </script>
</body>
</html>"""


@limiter.exempt
@app.route("/api/word-addon/install", methods=["GET", "OPTIONS"])
def word_addon_install():
    """Serve add-in installation instructions page."""
    if request.method == "OPTIONS":
        return _office_cors(Response())
    return _office_cors(Response(_INSTALL_HTML, mimetype="text/html"))


@limiter.exempt
@app.route("/api/word-addon/content", methods=["GET", "OPTIONS"])
@jwt_required(optional=True)
def word_addon_content():
    """Return placeholder content snippets for insert-into-document buttons."""
    if request.method == "OPTIONS":
        return _office_cors(jsonify({}))
    content_type = request.args.get("type", "").lower()
    snippets = {
        "title": {"text": "Your Paper Title Here"},
        "abstract": {"text": "This paper presents a novel approach to..."},
        "section": {"text": "## Introduction\n\nThis section introduces the problem statement and motivation behind this work."},
    }
    snippet = snippets.get(content_type)
    if not snippet:
        return _office_cors(jsonify({"error": "Unknown content type"})), 400
    return _office_cors(jsonify(snippet))


# ─── Version endpoint ───────────────────────────────────────────────────────────
@app.route("/api/version", methods=["GET"])
def api_version():
    import os, json
    base = os.path.join(os.path.dirname(__file__), "..", "frontend", "public")
    try:
        with open(os.path.join(base, "version-history.json"), "r") as f:
            return jsonify(json.load(f))
    except:
        pass
    return jsonify({"version": "0.0.0", "released": "", "title": "", "changes": []})


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("BACKEND_PORT", 8001))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    log.info("=" * 60)
    log.info("PaperFull API starting on port %d", port)
    log.info("🚀 PaperFull API running on http://localhost:%d", port)
    app.run(host="127.0.0.1", port=port, debug=debug, use_reloader=False, threaded=True)
