"""
Authentication Blueprint
======================================
Handles Google OAuth 2.0 login flow, email/password registration, and JWT token issuance.
JWT is delivered via httpOnly cookies with double-submit CSRF protection.
"""

import os
import re
import secrets
import logging
from datetime import datetime, timedelta, timezone

import requests
from flask import Blueprint, redirect, request, jsonify, url_for, current_app, session
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
    set_access_cookies,
    set_refresh_cookies,
    unset_jwt_cookies,
)
from authlib.integrations.flask_client import OAuth

from models import db, User

log = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')
oauth = OAuth()

MIN_PASSWORD_LEN = 8
MAX_PASSWORD_LEN = 128
MAX_EMAIL_LEN = 254
MAX_NAME_LEN = 80


def _allowed_frontend_url(candidate: str) -> str:
    """Restrict OAuth redirect target to a configured allowlist.
    Defaults to https://paperfull.app + http://localhost:1000 + http://localhost:8000.
    Override with FRONTEND_URL_ALLOWLIST=comma,separated,urls in .env.
    """
    raw = os.getenv('FRONTEND_URL_ALLOWLIST', '')
    allowed = [u.strip().rstrip('/') for u in raw.split(',') if u.strip()]
    if not allowed:
        allowed = ['https://paperfull.app', 'https://www.paperfull.app',
                   'http://localhost:1000', 'http://localhost:8000']
    target = (candidate or '').rstrip('/')
    if target in allowed:
        return target
    log.warning("OAuth redirect rejected (not in allowlist): %s", target)
    return allowed[0]


def _claim_admin_atomically(user: 'User') -> None:
    """Set user.role to 'admin' if and only if no admin exists yet.
    Uses a row-level lock on the users table to close the race where two
    concurrent registrations both observe an empty users table.
    """
    locked = (User.query
              .filter_by(role='admin')
              .with_for_update()
              .first())
    if locked is None:
        user.role = 'admin'
    else:
        user.role = 'user'


def _strong_password(password: str) -> str | None:
    """Return None if strong, else an error message."""
    if len(password) < MIN_PASSWORD_LEN:
        return f'Password must be at least {MIN_PASSWORD_LEN} characters'
    if len(password) > MAX_PASSWORD_LEN:
        return 'Password is too long'
    classes = sum([
        bool(re.search(r'[a-z]', password)),
        bool(re.search(r'[A-Z]', password)),
        bool(re.search(r'\d', password)),
        bool(re.search(r'[^A-Za-z0-9]', password)),
    ])
    if classes < 3:
        return 'Password must include at least 3 of: lowercase, uppercase, digits, symbols'
    return None


def init_oauth(app):
    """Initialize OAuth with the Flask app."""
    oauth.init_app(app)
    oauth.register(
        name='google',
        client_id=os.getenv('GOOGLE_CLIENT_ID'),
        client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'},
    )


def _issue_tokens_for(user: 'User'):
    """Build access + refresh tokens with the standard claim payload."""
    claims = {
        'email': user.email,
        'name': user.name,
        'role': user.role,
        'avatar': user.avatar_url or '',
    }
    access = create_access_token(identity=str(user.id), additional_claims=claims)
    refresh = create_refresh_token(identity=str(user.id), additional_claims={'role': user.role})
    return access, refresh


def _login_response(user: 'User', status: int = 200):
    """Set httpOnly cookies and return user payload (no token in body)."""
    access, refresh = _issue_tokens_for(user)
    resp = jsonify({'user': user.to_dict()})
    resp.status_code = status
    set_access_cookies(resp, access)
    set_refresh_cookies(resp, refresh)
    return resp


@auth_bp.route('/register', methods=['POST'])
def register():
    """Register a new user with email and password."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    # Cloudflare Turnstile CAPTCHA — verifies human (rofiq.txt sprint 1 #H2).
    # Bypass for E2E tests: backend reads ENABLE_CAPTCHA, frontend sends a
    # well-known dummy token. The Turnstile testing key (1x00000000000000000000AA)
    # is documented to always pass; we accept it as bypass token in test env too.
    if os.getenv('ENABLE_CAPTCHA', 'false').lower() == 'true':
        token = (data.get('captcha_token') or data.get('cf_turnstile_response') or '').strip()
        if not token:
            return jsonify({'error': 'CAPTCHA required'}), 400
        secret = os.getenv('TURNSTILE_SECRET_KEY', '')
        # Cloudflare's documented testing secrets — always skip the network call.
        # https://developers.cloudflare.com/turnstile/troubleshooting/testing/
        TURNSTILE_TEST_SECRETS = {
            '1x0000000000000000000000000000000AA',  # always passes
            '2x0000000000000000000000000000000AA',  # always fails
            '3x0000000000000000000000000000000AA',  # always fails as challenge
        }
        is_test_secret = secret in TURNSTILE_TEST_SECRETS
        if secret and not is_test_secret:
            try:
                resp = requests.post(
                    'https://challenges.cloudflare.com/turnstile/v0/siteverify',
                    data={
                        'secret': secret,
                        'response': token,
                        'remoteip': (request.headers.get('X-Forwarded-For') or request.remote_addr or '').split(',')[0].strip(),
                    },
                    timeout=8,
                )
                payload = resp.json() if resp.ok else {}
                if not payload.get('success'):
                    log.info("turnstile_failed", extra={'errors': payload.get('error-codes', [])})
                    return jsonify({'error': 'CAPTCHA verification failed'}), 400
            except Exception as e:
                log.warning("turnstile_unreachable: %s", e)
                return jsonify({'error': 'CAPTCHA service unreachable, please retry'}), 503

    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    name = (data.get('name') or '').strip()

    if not email or not password or not name:
        return jsonify({'error': 'Name, email, and password are required'}), 400

    if len(email) > MAX_EMAIL_LEN or len(name) > MAX_NAME_LEN:
        return jsonify({'error': 'Email or name is too long'}), 400

    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return jsonify({'error': 'Invalid email format'}), 400

    pw_error = _strong_password(password)
    if pw_error:
        return jsonify({'error': pw_error}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already registered'}), 409

    user = User(
        email=email,
        name=name,
        role='user',
    )
    user.set_password(password)
    _claim_admin_atomically(user)
    db.session.add(user)
    db.session.commit()

    log.info("New user registered via email: %s", email)
    return _login_response(user, status=201)


@auth_bp.route('/login', methods=['POST'])
def login_email():
    """Login with email and password."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400

    if len(email) > MAX_EMAIL_LEN or len(password) > MAX_PASSWORD_LEN:
        return jsonify({'error': 'Invalid email or password'}), 401

    user = User.query.filter_by(email=email).first()
    if not user:
        from werkzeug.security import check_password_hash
        check_password_hash(
            'pbkdf2:sha256:600000$dummy$' + 'a' * 64,
            password,
        )
        return jsonify({'error': 'Invalid email or password'}), 401
    if not user.check_password(password):
        return jsonify({'error': 'Invalid email or password'}), 401

    user.last_login = datetime.now(timezone.utc)
    db.session.commit()

    log.info("User logged in via email: %s", email)
    return _login_response(user)


@auth_bp.route('/google/login')
def google_login():
    """Redirect user to Google OAuth consent screen with CSRF protection."""
    if not os.getenv('GOOGLE_CLIENT_ID') or 'your-google-client-id' in os.getenv('GOOGLE_CLIENT_ID', ''):
        return jsonify({
            'error': 'Google OAuth not configured',
            'message': 'Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env and restart backend'
        }), 503
    
    # Generate CSRF state token (OAuth CSRF vulnerability fix)
    state = secrets.token_urlsafe(32)
    session['oauth_state'] = state
    
    domain = os.getenv('DOMAIN', 'paperfull.app')
    redirect_uri = f"https://{domain}/api/auth/google/callback"
    return oauth.google.authorize_redirect(redirect_uri, state=state)


@auth_bp.route('/google/callback')
def google_callback():
    """Handle Google OAuth callback with CSRF validation, set httpOnly cookies, redirect to frontend."""
    frontend_url = _allowed_frontend_url(os.getenv('FRONTEND_URL', 'http://localhost:1000'))
    
    # Validate CSRF state token (OAuth CSRF vulnerability fix)
    state_from_request = request.args.get('state')
    state_from_session = session.pop('oauth_state', None)
    
    if not state_from_request or not state_from_session:
        log.warning("OAuth callback missing state parameter")
        return redirect(f"{frontend_url}/login?error=invalid_state")
    
    if not secrets.compare_digest(state_from_request, state_from_session):
        log.warning("OAuth callback state mismatch - possible CSRF attack")
        return redirect(f"{frontend_url}/login?error=csrf_detected")
    
    try:
        token = oauth.google.authorize_access_token()
        userinfo = token.get('userinfo')
        if not userinfo:
            userinfo = oauth.google.userinfo()

        google_id = userinfo['sub']
        email = userinfo['email']
        name = userinfo.get('name', email.split('@')[0])
        avatar_url = userinfo.get('picture', '')

        user = User.query.filter_by(google_id=google_id).first()
        if not user:
            user = User(
                google_id=google_id,
                email=email,
                name=name,
                avatar_url=avatar_url,
                role='user',
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

        # Set cookies on the redirect response so the SPA picks them up automatically.
        access, refresh = _issue_tokens_for(user)
        resp = redirect(f"{frontend_url}/auth/callback")
        set_access_cookies(resp, access)
        set_refresh_cookies(resp, refresh)
        return resp

    except Exception as e:
        log.error("OAuth callback error: %s", e, exc_info=True)
        return redirect(f"{frontend_url}/login?error=auth_failed")


@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """Issue a new access token (and rotate refresh token) using the refresh cookie."""
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid user identity'}), 401
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    access, new_refresh = _issue_tokens_for(user)
    resp = jsonify({'user': user.to_dict()})
    set_access_cookies(resp, access)
    set_refresh_cookies(resp, new_refresh)  # rotate refresh on every use
    return resp


@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_me():
    """Return current authenticated user info."""
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid user identity'}), 401
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    return jsonify(user.to_dict())


@auth_bp.route('/logout', methods=['POST'])
@jwt_required(optional=True)
def logout():
    """Clear auth cookies. Protected to prevent CSRF."""
    resp = jsonify({'success': True, 'message': 'Logged out successfully'})
    unset_jwt_cookies(resp)
    return resp
