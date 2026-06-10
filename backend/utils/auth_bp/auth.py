"""
Authentication Blueprint
======================================
Handles Google OAuth 2.0 login flow, email/password registration, and JWT token issuance.
JWT is delivered via httpOnly cookies with double-submit CSRF protection.
"""

import base64
import json
import hashlib
import hmac
import logging
import os
import re
import secrets
from datetime import datetime, timezone
from urllib.parse import urlsplit

import requests
from authlib.integrations.flask_client import OAuth
from flask import Blueprint, current_app, jsonify, redirect, request, session
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
    jwt_required,
    set_access_cookies,
    set_refresh_cookies,
    unset_jwt_cookies,
)

from database.models import User, db

log = logging.getLogger(__name__)

auth = Blueprint("auth", __name__, url_prefix="/api/auth")
oauth = OAuth()

MIN_PASSWORD_LEN = 8
MAX_PASSWORD_LEN = 128
MAX_EMAIL_LEN = 254
MAX_NAME_LEN = 80


def _frontend_allowlist() -> list[str]:
    raw = os.getenv("FRONTEND_URL_ALLOWLIST") or os.getenv("ALLOWED_FRONTEND_URLS", "")
    allowed = [u.strip().rstrip("/") for u in raw.split(",") if u.strip()]
    if allowed:
        return allowed
    return [
        "https://paperfull.app",
        "https://www.paperfull.app",
        "http://localhost:1000",
        "http://localhost:8000",
    ]


def _allowed_frontend_url(candidate: str) -> str:
    allowed = _frontend_allowlist()
    target = (candidate or "").rstrip("/")
    if target in allowed:
        return target
    log.warning("OAuth redirect rejected (not in allowlist): %s", target)
    return allowed[0]


def _allowed_redirect_url(candidate: str) -> str | None:
    target = (candidate or "").strip().rstrip("/")
    if not target:
        return None
    parsed = urlsplit(target)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        log.warning("OAuth redirect rejected (invalid URL): %s", target)
        return None
    origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    if origin in _frontend_allowlist():
        return target
    log.warning("OAuth redirect rejected (origin not in allowlist): %s", target)
    return None


def _redirect_origin(target: str) -> str:
    parsed = urlsplit(target)
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def _allowed_google_emails() -> set[str]:
    raw = os.getenv("GOOGLE_ALLOWED_EMAILS", "")
    return {email.strip().lower() for email in raw.split(",") if email.strip()}


def _google_email_allowed(email: str) -> bool:
    allowed = _allowed_google_emails()
    return not allowed or email.strip().lower() in allowed


def _claim_admin_atomically(user: "User") -> None:
    locked = User.query.filter_by(role="admin").with_for_update().first()
    if locked is None:
        user.role = "admin"
    else:
        user.role = "user"


def _strong_password(password: str) -> str | None:
    if len(password) < MIN_PASSWORD_LEN:
        return f"Password must be at least {MIN_PASSWORD_LEN} characters"
    if len(password) > MAX_PASSWORD_LEN:
        return "Password is too long"
    classes = sum(
        [
            bool(re.search(r"[a-z]", password)),
            bool(re.search(r"[A-Z]", password)),
            bool(re.search(r"\d", password)),
            bool(re.search(r"[^A-Za-z0-9]", password)),
        ]
    )
    if classes < 3:
        return "Password must include at least 3 of: lowercase, uppercase, digits, symbols"
    return None


def _make_signed_state(redirect_to: str | None = None) -> str:
    if redirect_to:
        state_payload = {"nonce": secrets.token_urlsafe(32), "redirect_to": redirect_to}
        state = base64.urlsafe_b64encode(
            json.dumps(state_payload, separators=(",", ":")).encode()
        ).decode().rstrip("=")
    else:
        state = secrets.token_urlsafe(32)
    sig = hmac.new(
        current_app.config["SECRET_KEY"].encode(), state.encode(), hashlib.sha256
    ).hexdigest()
    payload = f"{state}.{sig}".encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _verify_signed_state(signed_state: str) -> str | None:
    try:
        padded = signed_state + "=" * (-len(signed_state) % 4)
        decoded = base64.urlsafe_b64decode(padded)
        state_bytes, signature_hex = decoded.rsplit(b".", 1)
        expected = hmac.new(
            current_app.config["SECRET_KEY"].encode(), state_bytes, hashlib.sha256
        ).hexdigest()
        if secrets.compare_digest(signature_hex.decode(), expected):
            return state_bytes.decode()
    except Exception:
        pass
    return None

def _state_redirect_to(verified_state: str | None) -> str | None:
    if not verified_state:
        return None
    try:
        padded = verified_state + "=" * (-len(verified_state) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        return _allowed_redirect_url(payload.get("redirect_to", ""))
    except Exception:
        return None


def init_oauth(app):
    oauth.init_app(app)
    oauth.register(
        name="google",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


def _google_callback_url() -> str:
    redirect_uri = os.getenv("GOOGLE_CALLBACK_URL")
    if redirect_uri:
        return redirect_uri
    domain = os.getenv("DOMAIN", "paperfull.app")
    protocol = "http" if "localhost" in domain else "https"
    return f"{protocol}://{domain}/api/auth/google/callback"


def _exchange_google_code(code: str, redirect_uri: str) -> dict:
    token_resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=15,
    )
    token_resp.raise_for_status()
    token = token_resp.json()
    userinfo_resp = requests.get(
        "https://openidconnect.googleapis.com/v1/userinfo",
        headers={"Authorization": f"Bearer {token['access_token']}"},
        timeout=15,
    )
    userinfo_resp.raise_for_status()
    return userinfo_resp.json()


def _issue_tokens_for(user: "User"):
    claims = {
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "avatar": user.avatar_url or "",
    }
    access = create_access_token(identity=str(user.id), additional_claims=claims)
    refresh = create_refresh_token(identity=str(user.id), additional_claims={"role": user.role})
    return access, refresh


def _login_response(user: "User", status: int = 200):
    access, refresh = _issue_tokens_for(user)
    resp = jsonify({
        "user": user.to_dict(),
        "access_token": access,
        "refresh_token": refresh
    })
    resp.status_code = status
    set_access_cookies(resp, access)
    set_refresh_cookies(resp, refresh)
    return resp


@auth.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body required"}), 400

    if os.getenv("ENABLE_CAPTCHA", "false").lower() == "true":
        token = (data.get("captcha_token") or data.get("cf_turnstile_response") or "").strip()
        if not token:
            return jsonify({"error": "CAPTCHA required"}), 400
        secret = os.getenv("TURNSTILE_SECRET_KEY", "")
        TURNSTILE_TEST_SECRETS = {
            "1x0000000000000000000000000000000AA",
            "2x0000000000000000000000000000000AA",
            "3x0000000000000000000000000000000AA",
        }
        is_test_secret = secret in TURNSTILE_TEST_SECRETS
        if secret and not is_test_secret:
            try:
                resp = requests.post(
                    "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                    data={
                        "secret": secret,
                        "response": token,
                        "remoteip": (
                            request.headers.get("X-Forwarded-For") or request.remote_addr or ""
                        )
                        .split(",")[0]
                        .strip(),
                    },
                    timeout=8,
                )
                payload = resp.json() if resp.ok else {}
                if not payload.get("success"):
                    log.info("turnstile_failed", extra={"errors": payload.get("error-codes", [])})
                    return jsonify({"error": "CAPTCHA verification failed"}), 400
            except Exception as e:
                log.warning("turnstile_unreachable: %s", e)
                return jsonify({"error": "CAPTCHA service unreachable, please retry"}), 503

    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    name = (data.get("name") or "").strip()

    if not email or not password or not name:
        return jsonify({"error": "Name, email, and password are required"}), 400

    if len(email) > MAX_EMAIL_LEN or len(name) > MAX_NAME_LEN:
        return jsonify({"error": "Email or name is too long"}), 400

    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return jsonify({"error": "Invalid email format"}), 400

    pw_error = _strong_password(password)
    if pw_error:
        return jsonify({"error": pw_error}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already registered"}), 409

    user = User(
        email=email,
        name=name,
        role="user",
    )
    user.set_password(password)
    _claim_admin_atomically(user)
    db.session.add(user)
    db.session.commit()

    log.info("New user registered via email: %s", email)
    return _login_response(user, status=201)


@auth.route("/login", methods=["POST"])
def login_email():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body required"}), 400

    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    if len(email) > MAX_EMAIL_LEN or len(password) > MAX_PASSWORD_LEN:
        return jsonify({"error": "Invalid email or password"}), 401

    user = User.query.filter_by(email=email).first()
    if not user:
        from werkzeug.security import check_password_hash

        check_password_hash(
            "pbkdf2:sha256:600000$dummy$" + "a" * 64,
            password,
        )
        return jsonify({"error": "Invalid email or password"}), 401
    if not user.check_password(password):
        return jsonify({"error": "Invalid email or password"}), 401

    user.last_login = datetime.now(timezone.utc)
    db.session.commit()

    log.info("User logged in via email: %s", email)
    return _login_response(user)


@auth.route("/google/login")
def google_login():
    if not os.getenv("GOOGLE_CLIENT_ID") or "your-google-client-id" in os.getenv(
        "GOOGLE_CLIENT_ID", ""
    ):
        return (
            jsonify(
                {
                    "error": "Google OAuth not configured",
                    "message": "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env and restart backend",
                }
            ),
            503,
        )

    redirect_to = _allowed_redirect_url(request.args.get("redirect_to", ""))
    signed_state = _make_signed_state(redirect_to)
    if redirect_to:
        session[f"oauth_redirect:{signed_state}"] = redirect_to
    log.info("OAuth login - Generated signed state (length=%d)", len(signed_state))

    redirect_uri = _google_callback_url()

    log.info("OAuth login - Redirect URI: %s", redirect_uri)
    resp = oauth.google.authorize_redirect(redirect_uri, state=signed_state)
    session.modified = True
    return resp


@auth.route("/google/callback")
def google_callback():
    frontend_url = _allowed_frontend_url(os.getenv("FRONTEND_URL", "http://localhost:1000"))

    google_error = request.args.get("error")
    error_description = request.args.get("error_description", "")
    if google_error:
        log.warning("OAuth callback - Google returned error: %s (%s)",
                     google_error, error_description)
        if google_error == "access_denied":
            return redirect(f"{frontend_url}/login?error=google_denied")
        return redirect(f"{frontend_url}/login?error=auth_failed")

    signed_state = request.args.get("state")
    if not signed_state:
        log.warning("OAuth callback - Missing state parameter")
        return redirect(f"{frontend_url}/login?error=invalid_state")

    verified_state = _verify_signed_state(signed_state)
    if not verified_state:
        log.warning("OAuth callback - Invalid state signature")
        return redirect(f"{frontend_url}/login?error=csrf_detected")

    log.info("OAuth callback - State signature verified OK")
    redirect_to = _allowed_redirect_url(session.pop(f"oauth_redirect:{signed_state}", "")) or _state_redirect_to(verified_state)
    if redirect_to:
        frontend_url = _redirect_origin(redirect_to)

    try:
        from authlib.integrations.base_client.framework_integration import FrameworkIntegration

        _fw = FrameworkIntegration("google")
        existing_state_data = _fw.get_state_data(session, signed_state)
        if existing_state_data:
            token = oauth.google.authorize_access_token()
            userinfo = token.get("userinfo")
            if not userinfo:
                userinfo = oauth.google.userinfo()
        else:
            code = request.args.get("code")
            if not code:
                log.warning("OAuth callback - Missing session and authorization code")
                return redirect(f"{frontend_url}/login?error=session_expired")
            log.warning("OAuth callback - Session state missing; using signed-state code exchange fallback")
            userinfo = _exchange_google_code(code, _google_callback_url())

        google_id = userinfo["sub"]
        email = userinfo["email"]
        if not _google_email_allowed(email):
            log.warning("OAuth callback - Google email not allowed: %s", email)
            return redirect(f"{frontend_url}/login?error=email_not_allowed")

        name = userinfo.get("name", email.split("@")[0])
        avatar_url = userinfo.get("picture", "")

        user = User.query.filter_by(google_id=google_id).first()
        if not user:
            user = User(
                google_id=google_id,
                email=email,
                name=name,
                avatar_url=avatar_url,
                role="user",
            )
            _claim_admin_atomically(user)
            db.session.add(user)
            log.info("New user registered: %s (role=%s)", email, user.role)
        else:
            user.email = email
            user.name = name
            user.avatar_url = avatar_url
            user.last_login = datetime.now(timezone.utc)
            log.info("User logged in: %s", email)

        db.session.commit()

        access, refresh = _issue_tokens_for(user)
        resp = redirect(redirect_to or f"{frontend_url}/auth/callback")
        set_access_cookies(resp, access)
        set_refresh_cookies(resp, refresh)
        log.info("OAuth success - redirecting to %s with cookies set", frontend_url)
        return resp

    except Exception as e:
        log.error("OAuth callback error: %s", e, exc_info=True)
        error_code = "auth_failed"
        error_lower = str(e).lower()
        if "access_denied" in error_lower:
            error_code = "google_denied"
        elif "mismatch" in error_lower or "state" in error_lower:
            error_code = "csrf_detected"
        return redirect(f"{frontend_url}/login?error={error_code}")


@auth.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid user identity"}), 401

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    access, new_refresh = _issue_tokens_for(user)
    resp = jsonify({"user": user.to_dict()})
    set_access_cookies(resp, access)
    set_refresh_cookies(resp, new_refresh)
    return resp


@auth.route("/me", methods=["GET"])
@jwt_required()
def get_me():
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid user identity"}), 401

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(user.to_dict())


@auth.route("/logout", methods=["POST"])
@jwt_required(optional=True)
def logout():
    resp = jsonify({"success": True, "message": "Logged out successfully"})
    unset_jwt_cookies(resp)
    return resp
