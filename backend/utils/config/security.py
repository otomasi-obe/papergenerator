"""
Security Configuration
======================
Security headers, error handlers, and CSRF protection setup.
"""

from flask import jsonify, request


def setup_error_handlers(app):
    """Set up custom error handlers for better error responses."""
    
    @app.errorhandler(413)
    def _on_413(_e):
        """Friendlier 413 — Werkzeug's default returns an HTML page that the chat
        upload code treats as a generic network error. Serve JSON so the frontend
        can show "file terlalu besar" instead of "Network error"."""
        return (
            jsonify(
                {
                    "error": "Payload terlalu besar",
                    "hint": (
                        f"Total upload melebihi {app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)} MB. "
                        "Coba upload file lebih sedikit atau pisah jadi beberapa kali upload."
                    ),
                    "code": "PAYLOAD_TOO_LARGE",
                }
            ),
            413,
        )


def setup_security_headers(app):
    """Set up security headers for all responses."""
    
    @app.after_request
    def _security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        
        # Content Security Policy
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self'; "
            "font-src 'self' data:; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        response.headers.setdefault("Content-Security-Policy", csp)
        
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


def setup_auth_rate_limits(limiter, auth_bp):
    """Apply stricter rate limits to auth endpoints to defend against credential stuffing."""
    limiter.limit("10 per minute")(auth_bp)


def init_security(app, limiter, auth_bp):
    """Initialize all security configurations."""
    setup_error_handlers(app)
    setup_security_headers(app)
    setup_auth_rate_limits(limiter, auth_bp)
