"""
Flask Extensions Initialization
================================
Centralized initialization for CORS, JWT, rate limiting, and database extensions.
"""

import logging
import os

from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sqlalchemy import event
from sqlalchemy.engine import Engine

from database.models import db

log = logging.getLogger(__name__)


def init_cors(app):
    """Initialize CORS with appropriate origins."""
    cors_origins = ["https://paperfull.app", "https://www.paperfull.app"]
    if app.config.get("ENV") != "production" and not app.config.get("PRODUCTION"):
        cors_origins.extend(["http://localhost:1000", "http://localhost:5173"])
    CORS(app, supports_credentials=True, origins=cors_origins)


def init_database(app):
    """Initialize database and set up PostgreSQL session safeguards."""
    db.init_app(app)
    
    # PostgreSQL session safeguards
    # Hindari sesi nyangkut: timeout query 30 dtk, idle txn 5 menit, lock 5 dtk.
    # Hanya aktif untuk koneksi psycopg (PostgreSQL); SQLite/test akan di-skip.
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
            log.exception("failed to set pg session defaults")


def init_jwt(app):
    """Initialize JWT manager."""
    return JWTManager(app)


def init_rate_limiter(app, in_tests=False):
    """Initialize rate limiter with Redis or memory storage."""
    from flask import jsonify, request
    
    ratelimit_storage = os.getenv("RATELIMIT_STORAGE_URI")
    if not ratelimit_storage:
        if app.config.get("ENV") == "production" or app.config.get("PRODUCTION"):
            raise RuntimeError(
                "RATELIMIT_STORAGE_URI must be set in production. "
                "Use Redis: redis://localhost:6379 or redis://user:pass@host:port/db"
            )
        else:
            # Development/testing: allow memory storage
            ratelimit_storage = "memory://"
            log.warning(
                "Using memory:// for rate limiting (development only). "
                "Set RATELIMIT_STORAGE_URI=redis://... for production."
            )

    def rate_limit_handler(request_limit):
        """Custom handler for rate limit breaches - returns JSON response."""
        from core.errors import ErrorCategory, ErrorCode
        from monitoring.observability_v2 import RATE_LIMIT_BREACHES

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
        enabled=not in_tests,
        default_limits=["1000 per minute"],
        storage_uri=ratelimit_storage,
        strategy="fixed-window",
        on_breach=rate_limit_handler,
    )
    
    return limiter


def init_extensions(app, in_tests=False):
    """Initialize all Flask extensions."""
    init_cors(app)
    init_database(app)
    jwt = init_jwt(app)
    limiter = init_rate_limiter(app, in_tests)
    
    # Initialize OAuth (imported from auth_bp)
    from api.auth_bp import init_oauth
    init_oauth(app)
    
    return jwt, limiter
