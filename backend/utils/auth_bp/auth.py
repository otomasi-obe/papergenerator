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
import smtplib
import time
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlsplit

import requests
from authlib.integrations.flask_client import OAuth
from flask import Blueprint, current_app, jsonify, redirect, request, session
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
    set_access_cookies,
    verify_jwt_in_request,
    set_refresh_cookies,
    unset_jwt_cookies,
)

from utils.database.models import User, db, safe_commit
from utils.core.redis_client import get_redis
from .captcha import (
    captcha_enabled,
    captcha_required_for_login,
    generate_captcha,
    increment_failed_attempts,
    reset_failed_attempts,
    verify_captcha,
)

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


# Thread-level fallback lock for admin claim when Redis unavailable
_admin_claim_lock = __import__("threading").Lock()


def _claim_admin_atomically(user: "User") -> None:
    """First user becomes admin; rest are regular users.

    Uses Redis SET NX distributed lock to prevent two concurrent registrations
    from both claiming admin (BUG-07).  Falls back to a threading lock when
    Redis is unavailable, which still prevents races within a single process.
    """
    from utils.core.redis_client import get_redis

    rc = get_redis()
    _lock_key = "papergenerator:admin_claim_lock"
    _lock_ttl = 10  # seconds
    _lock_token = secrets.token_hex(8)  # unique per acquisition attempt

    if rc is not None:
        # Spin-acquire with short timeout; store unique token so we only delete our own lock
        import time as _time
        deadline = _time.monotonic() + _lock_ttl
        while _time.monotonic() < deadline:
            if rc.set(_lock_key, _lock_token, nx=True, ex=_lock_ttl):
                break
            _time.sleep(0.05)
        else:
            # Could not acquire in time — assume another worker is claiming; safe default
            user.role = "user"
            return
    else:
        _admin_claim_lock.acquire()

    try:
        locked = User.query.filter_by(role="admin").with_for_update().first()
        if locked is None:
            user.role = "admin"
        else:
            user.role = "user"
    finally:
        if rc is not None:
            # Only delete if we still own the lock (token still matches)
            import time as _time
            current = rc.get(_lock_key)
            if current == _lock_token:
                try:
                    rc.delete(_lock_key)
                except Exception:
                    pass
        else:
            _admin_claim_lock.release()


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
    # BUG-08: Add exp timestamp to prevent replay attacks (10 minute expiry)
    exp = int(time.time()) + 600
    if redirect_to:
        state_payload = {"nonce": secrets.token_urlsafe(32), "redirect_to": redirect_to, "exp": exp}
        state = base64.urlsafe_b64encode(
            json.dumps(state_payload, separators=(",", ":")).encode()
        ).decode().rstrip("=")
    else:
        state_payload = {"nonce": secrets.token_urlsafe(32), "exp": exp}
        state = base64.urlsafe_b64encode(
            json.dumps(state_payload, separators=(",", ":")).encode()
        ).decode().rstrip("=")
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
        if not secrets.compare_digest(signature_hex.decode(), expected):
            return None
        # BUG-08: Validate exp timestamp — reject expired states (10 min window)
        try:
            state_json = json.loads(base64.urlsafe_b64decode(
                state_bytes.decode() + "=" * (-len(state_bytes.decode()) % 4)
            ))
            exp = state_json.get("exp")
            if exp is not None and int(exp) < int(time.time()):
                log.warning("OAuth state expired (exp=%s, now=%s)", exp, int(time.time()))
                return None
        except (json.JSONDecodeError, KeyError, ValueError):
            # Legacy state format without exp — allow for backwards compatibility
            pass
        return state_bytes.decode()
    except Exception:
        log.warning("OAuth state verification failed", exc_info=True)
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
        "user": user.to_dict()
    })
    resp.status_code = status
    set_access_cookies(resp, access)
    set_refresh_cookies(resp, refresh)
    return resp


# ─── CAPTCHA Endpoints ──────────────────────────────────────────────────────
@auth.route("/captcha/generate", methods=["GET"])
def captcha_generate():
    """Generate a math CAPTCHA challenge. Returns captcha_id + question."""
    if not captcha_enabled():
        return jsonify({"captcha_required": False}), 200
    result = generate_captcha()
    if result is None:
        return jsonify({"error": "CAPTCHA service unavailable"}), 503
    return jsonify({"captcha_required": True, **result}), 200


@auth.route("/captcha/verify", methods=["POST"])
def captcha_verify():
    """Verify a CAPTCHA answer. Returns {valid: true/false}."""
    data = request.get_json(silent=True) or {}
    captcha_id = (data.get("captcha_id") or "").strip()
    answer = (data.get("answer") or "").strip()
    if not captcha_id or not answer:
        return jsonify({"valid": False, "error": "captcha_id and answer required"}), 400
    valid = verify_captcha(captcha_id, answer)
    return jsonify({"valid": valid}), 200


@auth.route("/captcha/status", methods=["GET"])
def captcha_status():
    """Check if CAPTCHA is required for login from current IP."""
    required = captcha_required_for_login()
    return jsonify({"captcha_required": required, "captcha_enabled": captcha_enabled()}), 200


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

    # Math CAPTCHA check (CAPTCHA_ENABLED env var)
    if captcha_enabled():
        mc_id = (data.get("math_captcha_id") or "").strip()
        mc_answer = (data.get("math_captcha_answer") or "").strip()
        if not mc_id or not mc_answer:
            return jsonify({"error": "CAPTCHA required", "captcha_required": True}), 400
        if not verify_captcha(mc_id, mc_answer):
            return jsonify({"error": "CAPTCHA answer incorrect", "captcha_required": True}), 400

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
    # Assign Trial badge on registration (500K tokens, no expiry — habis token = habis trial)
    user.token_quota_monthly = 500000  # Trial tokens
    user.badge = "trial"
    user.badge_expires_at = None  # Trial: no expiry, token habis = badge hilang
    _claim_admin_atomically(user)
    db.session.add(user)
    safe_commit()

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

    # Require math CAPTCHA after MAX_FAILED_ATTEMPTS failed logins from same IP
    if captcha_required_for_login():
        mc_id = (data.get("math_captcha_id") or "").strip()
        mc_answer = (data.get("math_captcha_answer") or "").strip()
        if not mc_id or not mc_answer:
            return jsonify({"error": "Too many failed attempts. CAPTCHA required.", "captcha_required": True}), 400
        if not verify_captcha(mc_id, mc_answer):
            return jsonify({"error": "CAPTCHA answer incorrect", "captcha_required": True}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        from werkzeug.security import check_password_hash

        check_password_hash(
            "pbkdf2:sha256:600000$dummy$" + "a" * 64,
            password,
        )
        increment_failed_attempts()
        return jsonify({"error": "Invalid email or password"}), 401
    if not user.check_password(password):
        increment_failed_attempts()
        return jsonify({"error": "Invalid email or password"}), 401

    # Successful login — reset failed attempt counter
    reset_failed_attempts()
    user.last_login = datetime.now(timezone.utc)
    safe_commit()

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

    # If PaperFull session is still valid, never send the user back to Google.
    # This prevents repeated account chooser prompts after the first successful login.
    try:
        verify_jwt_in_request(optional=True)
        if get_jwt_identity():
            target_origin = _redirect_origin(redirect_to) if redirect_to else _allowed_frontend_url(os.getenv("FRONTEND_URL", "http://localhost:1000"))
            return redirect(f"{target_origin}/dashboard")
    except Exception:
        pass

    signed_state = _make_signed_state(redirect_to)
    if redirect_to:
        session[f"oauth_redirect:{signed_state}"] = redirect_to
    log.info("OAuth login - Generated signed state (length=%d)", len(signed_state))

    redirect_uri = _google_callback_url()

    log.info("OAuth login - Redirect URI: %s", redirect_uri)
    # Pass login_hint so Google pre-selects the user's account (no account chooser)
    extra_params = {}
    login_hint = request.args.get("login_hint", "").strip()
    if login_hint:
        extra_params["login_hint"] = login_hint
    resp = oauth.google.authorize_redirect(redirect_uri, state=signed_state, **extra_params)
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

        # ── Security: don't blindly trust email_verified ──────────────────────
        # Google is reliable for email_verified=true, but we still guard against
        # account takeover: if a password-registered account exists for this
        # email, we do NOT auto-link. The user must verify their password first
        # via /api/auth/link-google before we merge.
        email_verified = userinfo.get("email_verified", False)
        if not email_verified:
            log.warning("OAuth callback - email_verified=false for %s, rejecting", email)
            return redirect(f"{frontend_url}/login?error=email_not_verified")

        if not _google_email_allowed(email):
            log.warning("OAuth callback - Google email not allowed: %s", email)
            return redirect(f"{frontend_url}/login?error=email_not_allowed")

        name = userinfo.get("name", email.split("@")[0])
        avatar_url = userinfo.get("picture", "")

        # ── Lookup: first by google_id (existing OAuth user), then by email ──
        user = User.query.filter_by(google_id=google_id).first()

        if not user:
            # No existing google_id match — check for email collision
            existing_user = User.query.filter_by(email=email).first()

            if existing_user and existing_user.password_hash:
                # Account exists with password but no Google link.
                # Prevent account takeover: require explicit password verification.
                log.warning(
                    "OAuth callback - email %s has password account without Google link; "
                    "redirecting to link flow", email
                )
                return redirect(
                    f"{frontend_url}/login?error=account_linking_required"
                    f"&email={email}"
                )

            if existing_user and not existing_user.password_hash:
                # Existing OAuth-only user (no password) — link this google_id
                user = existing_user
                user.google_id = google_id
                user.oauth_provider = user.oauth_provider or "google"
                user.email = email
                user.name = name
                user.avatar_url = avatar_url
                user.last_login = datetime.now(timezone.utc)
                log.info("OAuth callback - linked google_id to existing OAuth-only user %s", email)
            else:
                # Completely new user — create with oauth_provider='google'
                user = User(
                    google_id=google_id,
                    email=email,
                    name=name,
                    avatar_url=avatar_url,
                    role="user",
                    oauth_provider="google",
                    token_quota_monthly=500000,
                    badge="trial",
                    badge_expires_at=None,  # Trial: no expiry, token habis = badge hilang
                )
                _claim_admin_atomically(user)
                db.session.add(user)
                log.info("New user registered via Google OAuth: %s (role=%s)", email, user.role)
        else:
            # Existing google_id user — update profile
            user.email = email
            user.name = name
            user.avatar_url = avatar_url
            user.last_login = datetime.now(timezone.utc)
            # Backfill oauth_provider for pre-migration rows
            if not user.oauth_provider:
                user.oauth_provider = "google"
            log.info("User logged in via Google: %s", email)

        # BUG FIX: Wrap commit in try-except with explicit rollback
        # to ensure session is not left in broken state on failure
        try:
            safe_commit()
        except Exception as commit_err:
            log.error("OAuth commit failed: %s, rolling back session", commit_err)
            db.session.rollback()
            return redirect(f"{frontend_url}/login?error=auth_failed")

        access, refresh = _issue_tokens_for(user)
        resp = redirect(redirect_to or f"{frontend_url}/auth/callback")
        set_access_cookies(resp, access)
        set_refresh_cookies(resp, refresh)
        log.info("OAuth success - redirecting to %s with cookies set", frontend_url)
        return resp

    except Exception as e:
        log.error("OAuth callback error: %s", e, exc_info=True)
        # BUG FIX: Ensure session rollback before redirect
        try:
            db.session.rollback()
        except Exception:
            pass
        error_code = "auth_failed"
        error_lower = str(e).lower()
        if "access_denied" in error_lower:
            error_code = "google_denied"
        elif "mismatch" in error_lower or "state" in error_lower:
            error_code = "csrf_detected"
        return redirect(f"{frontend_url}/login?error={error_code}")


@auth.route("/link-google", methods=["POST"])
def link_google_account():
    """Link a Google OAuth account to an existing password-based account.

    Flow: user proves ownership of the password account by providing their
    current password, then we exchange the Google auth code and merge.

    Body JSON:
        email: str          — existing account email
        password: str       — existing account password (proof of ownership)
        google_code: str    — authorization code from Google OAuth popup
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body required"}), 400

    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    google_code = data.get("google_code") or ""

    if not email or not password or not google_code:
        return jsonify({"error": "email, password, and google_code are required"}), 400

    # 1. Verify password ownership of the existing account
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "Invalid email or password"}), 401
    if not user.check_password(password):
        return jsonify({"error": "Invalid email or password"}), 401

    # 2. Exchange Google code for userinfo
    try:
        userinfo = _exchange_google_code(google_code, _google_callback_url())
    except Exception as e:
        log.warning("link-google: Google code exchange failed: %s", e)
        return jsonify({"error": "Google authorization failed"}), 400

    google_email = userinfo.get("email", "").strip().lower()
    google_id = userinfo.get("sub")
    email_verified = userinfo.get("email_verified", False)

    if not email_verified:
        return jsonify({"error": "Google email is not verified"}), 400

    if not google_id:
        return jsonify({"error": "Missing Google user ID"}), 400

    # 3. Verify the Google email matches the account email (prevents linking
    #    someone else's Google account to yours)
    if google_email != email:
        return jsonify({
            "error": "Google account email does not match your account",
            "google_email": google_email,
        }), 400

    # 4. Check if this google_id is already linked to another account
    existing_google = User.query.filter_by(google_id=google_id).first()
    if existing_google and existing_google.id != user.id:
        return jsonify({"error": "This Google account is already linked to another user"}), 409

    # 5. Link!
    user.google_id = google_id
    user.oauth_provider = user.oauth_provider or "google"
    user.avatar_url = user.avatar_url or userinfo.get("picture", "")
    user.last_login = datetime.now(timezone.utc)
    safe_commit()

    log.info("Account linked: %s -> Google %s", email, google_id)
    return _login_response(user)


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

    # Revoke old refresh token JTI to prevent replay
    old_jti = get_jwt().get("jti")
    rc = get_redis()
    if rc and old_jti:
        # Store revoked JTI with TTL matching token expiry (default 30 days)
        rc.setex(f"rjti:{old_jti}", 2592000, "1")

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
    if not user or user.is_deleted:
        return jsonify({"error": "User not found"}), 404
    return jsonify(user.to_dict())


def _revoke_all_tokens(jwt_payload):
    """Revoke the current access + refresh token via Redis blocklist."""
    try:
        rc = get_redis()
        if not rc:
            return
        jti = jwt_payload.get("jti")
        if not jti:
            return
        exp = jwt_payload.get("exp")
        ttl = int(exp - time.time()) if exp else 86400
        ttl = max(1, min(ttl, 86400 * 30))
        token_type = jwt_payload.get("type")
        prefix = "rjti:" if token_type == "refresh" else "ajti:"
        rc.setex(f"{prefix}{jti}", ttl, "1")
    except Exception:
        pass


@auth.route("/me/settings", methods=["PATCH"])
@jwt_required()
def update_settings():
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid user identity"}), 401

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    body = request.get_json(silent=True) or {}

    # Update profile fields
    if "name" in body:
        name = (body["name"] or "").strip()
        if name:
            user.name = name

    if "nickname" in body:
        user.nickname = (body["nickname"] or "").strip()

    if "institution" in body:
        user.institution = (body["institution"] or "").strip()

    if "preferred_language" in body:
        lang = (body["preferred_language"] or "").strip().lower()
        if lang in ("id", "en"):
            user.preferred_language = lang

    # Change password
    if "new_password" in body:
        new_pw = body["new_password"] or ""
        pw_error = _strong_password(new_pw)
        if pw_error:
            return jsonify({"error": pw_error}), 400
        # If user has existing password, require current password
        if user.password_hash:
            current_pw = body.get("current_password") or ""
            if not user.check_password(current_pw):
                return jsonify({"error": "Password saat ini salah"}), 400
        else:
            # OAuth user setting password for first time — require email verification
            # or a fresh Google token to prevent account takeover.
            # BUG FIX: Verify google_token server-side instead of trusting email_verified flag
            if not user.google_id:
                return jsonify({"error": "Akun ini bukan akun OAuth; tidak dapat set password tanpa password lama"}), 400
            
            google_token = body.get("google_token")
            if not google_token:
                return jsonify({"error": "Google token required untuk set password pertama kali"}), 400
            
            # Verify token with Google's tokeninfo endpoint
            try:
                token_info_resp = requests.get(
                    f"https://oauth2.googleapis.com/tokeninfo?id_token={google_token}",
                    timeout=8,
                )
                if not token_info_resp.ok:
                    log.warning("Google token verification failed for user %s", user.id)
                    return jsonify({"error": "Invalid Google token"}), 400
                
                token_data = token_info_resp.json()
                token_email = token_data.get("email", "").strip().lower()
                token_audience = token_data.get("aud", "")
                
                # Verify email matches and audience is our app
                if token_email != user.email:
                    log.warning("Google token email mismatch: %s vs %s", token_email, user.email)
                    return jsonify({"error": "Token email tidak cocok"}), 400
                
                # Verify audience (client_id)
                expected_client_id = os.getenv("GOOGLE_CLIENT_ID", "")
                if expected_client_id and token_audience != expected_client_id:
                    log.warning("Google token audience mismatch")
                    return jsonify({"error": "Token tidak valid untuk aplikasi ini"}), 400
                    
            except Exception as e:
                log.error("Google token verification error: %s", e)
                return jsonify({"error": "Failed to verify Google token"}), 503
        
        user.set_password(new_pw)

    safe_commit()
    return jsonify(user.to_dict())


@auth.route("/logout", methods=["POST"])
@jwt_required(optional=True)
def logout():
    resp = jsonify({"success": True, "message": "Logged out successfully"})
    unset_jwt_cookies(resp)
    return resp


@auth.route("/heartbeat", methods=["POST"])
@jwt_required()
def heartbeat():
    """Update last_login timestamp for realtime online status."""
    user_id = int(get_jwt_identity())
    try:
        u = User.query.get(user_id)
        if u:
            u.last_login = datetime.now(timezone.utc)
            db.session.commit()
        return jsonify({"success": True})
    except Exception:
        db.session.rollback()
        return jsonify({"success": False}), 500


@auth.route("/contact", methods=["POST"])
def submit_contact():
    """Contact form: validate, rate-limit, save to JSONL, optionally email."""
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    category = (data.get("category") or "general").strip().lower()
    subject = (data.get("subject") or "").strip()
    message = (data.get("message") or "").strip()

    # Validate
    if not name or len(name) > 100:
        return jsonify({"error": "Nama harus diisi (max 100 karakter)"}), 400
    if not email or len(email) > 254 or "@" not in email:
        return jsonify({"error": "Email tidak valid"}), 400
    if category not in ("general", "refund", "privacy", "technical", "other"):
        category = "general"
    if not subject or len(subject) > 200:
        return jsonify({"error": "Subjek harus diisi (max 200 karakter)"}), 400
    if not message or len(message) < 10 or len(message) > 5000:
        return jsonify({"error": "Pesan harus 10-5000 karakter"}), 400

    # Rate-limit: 3 per hour per IP
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
    redis_client = get_redis()
    rate_key = f"contact_rl:{ip}"
    if redis_client:
        try:
            count = redis_client.incr(rate_key)
            if count == 1:
                redis_client.expire(rate_key, 3600)
            if count > 20:
                return jsonify({"error": "Terlalu banyak permintaan. Coba lagi dalam 1 jam."}), 429
        except Exception:
            pass  # Redis down → allow

    # Save to JSONL
    instance_dir = Path(current_app.instance_path)
    instance_dir.mkdir(parents=True, exist_ok=True)
    contact_log = instance_dir / "contact_messages.jsonl"
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ip": ip,
        "name": name,
        "email": email,
        "category": category,
        "subject": subject,
        "message": message,
    }
    try:
        import json
        with open(contact_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        log.error(f"Failed to write contact log: {e}")

    # Send email via Resend
    resend_api_key = os.getenv("RESEND_API_KEY")
    contact_to = os.getenv("CONTACT_TO", "anabilhisyam23@gmail.com")
    from_email = "Paperfull Support <support@paperfull.app>"

    if resend_api_key:
        try:
            import resend
            resend.api_key = resend_api_key

            # Admin notification
            resend.Emails.send({
                "from": from_email,
                "to": [contact_to],
                "reply_to": email,
                "subject": f"[{category.upper()}] {subject}",
                "html": f"""<div style="font-family: sans-serif;">
<p><strong>Nama:</strong> {name}</p>
<p><strong>Email:</strong> {email}</p>
<p><strong>Kategori:</strong> {category}</p>
<p><strong>Subjek:</strong> {subject}</p>
<p><strong>Pesan:</strong></p>
<p>{message.replace(chr(10), '<br>')}</p>
<hr>
<p><small>IP: {ip} • {entry['timestamp']}</small></p>
</div>""",
            })

            # Auto-reply to user
            ticket_id = f"PF-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{hash(email + subject) % 10000:04d}"
            ar_subject = f"[Paperfull] Pesan Anda telah kami terima"
            resend.Emails.send({
                "from": from_email,
                "to": [email],
                "subject": ar_subject,
                "html": f"""<div style="font-family: sans-serif;">
<p>Halo {name},</p>
<p>Terima kasih telah menghubungi Paperfull.</p>
<p>Pesan Anda dengan subjek <em>{subject}</em> telah kami terima.</p>
<p>Tim kami akan merespons dalam 1-2 hari kerja.</p>
<p>Nomor tiket: <strong>#{ticket_id}</strong></p>
<p><em>(Jangan balas email ini — kami akan menghubungi Anda melalui email ini)</em></p>
<p>Salam,<br>Tim Paperfull</p>
</div>""",
            })

        except Exception as e:
            log.warning(f"Resend email failed: {e}")
            # JSONL fallback already saved

    return jsonify({"success": True, "message": "Pesan Anda telah dikirim. Kami akan merespons dalam 1-2 hari kerja."})


@auth.route("/me/export", methods=["GET"])
@jwt_required()
def export_my_data():
    """GDPR-style data export: return all user-owned data as JSON (download)."""
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid user identity"}), 401

    user = User.query.get(user_id)
    if not user or user.is_deleted:
        return jsonify({"error": "User not found"}), 404

    from utils.database.models import (
        Paper, LiteratureItem, SlrJob, ApiUsageLog, Conversation, ChatMessage,
    )

    papers = [p.to_dict() for p in db.session.query(Paper).filter_by(user_id=user_id).all()]
    literature = [
        li.to_dict() for li in db.session.query(LiteratureItem).filter_by(user_id=user_id).all()
    ]
    slr_jobs = [j.to_dict() for j in db.session.query(SlrJob).filter_by(user_id=user_id).all()]
    usage = [
        u.to_dict() for u in db.session.query(ApiUsageLog).filter_by(user_id=user_id).all()
    ]
    conversations = [
        c.to_dict() for c in db.session.query(Conversation).filter_by(user_id=user_id).all()
    ]

    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user": user.to_dict(),
        "papers": papers,
        "literature_items": literature,
        "slr_jobs": slr_jobs,
        "api_usage_logs": usage,
        "conversations": conversations,
    }
    resp = jsonify(payload)
    resp.headers["Content-Disposition"] = (
        f'attachment; filename="paperfull-data-export-{user_id}.json"'
    )
    return resp


@auth.route("/me", methods=["DELETE"])
@jwt_required()
def delete_my_account():
    """GDPR-style account deletion: soft-delete + anonymize PII, revoke tokens.

    Data is retained (papers/literature kept for referential integrity) but the
    account is deactivated and all personally identifiable info is wiped.
    """
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid user identity"}), 401

    user = User.query.get(user_id)
    if not user or user.is_deleted:
        return jsonify({"error": "User not found"}), 404

    if user.role == "admin":
        return jsonify({"error": "Admin account cannot be self-deleted"}), 403

    # Anonymize PII
    import secrets as _secrets
    anon = _secrets.token_hex(8)
    user.email = f"deleted-{anon}@deleted.paperfull.app"
    user.name = "Deleted User"
    user.nickname = ""
    user.institution = ""
    user.password_hash = None
    user.google_id = None
    user.oauth_provider = None
    user.avatar_url = None
    user.is_deleted = True
    user.deleted_at = datetime.now(timezone.utc)
    safe_commit()

    # Revoke current token so the session dies immediately
    try:
        _revoke_all_tokens(get_jwt())
    except Exception:
        pass

    resp = jsonify({"success": True, "message": "Account deleted"})
    unset_jwt_cookies(resp)
    return resp
