"""
DOKU Payment Gateway (SNAP) — QRIS integration for PaperFull.
Endpoints: get_token, generate_qris, query_qris, callback.
Docs: https://developers.doku.com/accept-payments/direct-api/snap/qris
"""

import os
import json
import hashlib
import hmac
import base64
import time
import uuid
import requests
import threading
from datetime import datetime, timezone, timedelta
from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from utils.database.models import db, User, Payment, safe_commit

doku_bp = Blueprint('doku', __name__, url_prefix='/api/payment/doku')

# ─── Token package mapping ───────────────────────────────────────────
TOKEN_PACKAGES = {
    0:        500000,   # Trial (gratis) - 500K token
    1000:     10,       # Test QRIS
    41000:    300000,   # Harian
    125000:   1200000,  # Mingguan (Pro)
    315000:   3500000,  # Bulanan (Elite)
}

# ─── In-memory B2B token cache ────────────────────────────────────────
_token_cache = {
    'access_token': None,
    'expires_at': 0,
}
_token_lock = threading.Lock()  # BUG-6 FIX: thread-safe token cache access

# ─── Config ───────────────────────────────────────────────────────────

def _get_config():
    env = os.getenv('DOKU_ENV', 'sandbox')
    base_url = 'https://api-sandbox.doku.com' if env == 'sandbox' else 'https://api.doku.com'
    return {
        'client_id': os.getenv('DOKU_CLIENT_ID'),
        'secret_key': os.getenv('DOKU_SECRET_KEY'),
        'base_url': base_url,
        'private_key_path': os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'keys', 'pkcs8.key'),
        'merchant_id': os.getenv('DOKU_MERCHANT_ID', ''),  # will discover via sandbox
        'terminal_id': os.getenv('DOKU_TERMINAL_ID', 'PF01'),
        'postal_code': os.getenv('DOKU_POSTAL_CODE', '60236'),
    }


def _load_private_key():
    """Load RSA private key from PEM file."""
    cfg = _get_config()
    with open(cfg['private_key_path'], 'rb') as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def _timestamp():
    """ISO8601 timestamp with +07:00 (WIB)."""
    now = datetime.now(timezone(timedelta(hours=7)))
    return now.strftime('%Y-%m-%dT%H:%M:%S+07:00')


def _external_id():
    """Numeric string, unique per day."""
    return str(int(time.time() * 1000)) + str(uuid.uuid4().int)[:8]


# ─── Asymmetric Signature (Get Token) ────────────────────────────────

def _asymmetric_signature(client_id: str, timestamp: str) -> str:
    """
    SHA256withRSA(privateKey, clientID|timestamp) → Base64.
    Used for Get Token B2B.
    """
    string_to_sign = f"{client_id}|{timestamp}"
    private_key = _load_private_key()
    signature = private_key.sign(
        string_to_sign.encode('utf-8'),
        padding.PKCS1v15(),
        hashes.SHA256()
    )
    return base64.b64encode(signature).decode('utf-8')


# ─── Symmetric Signature (Transactional) ─────────────────────────────

def _symmetric_signature(http_method: str, endpoint: str, access_token: str,
                         request_body: dict, timestamp: str) -> str:
    """
    HMAC_SHA512(secretKey, "POST:endpoint:accessToken:sha256(body):timestamp") → Base64.
    Used for all QRIS endpoints.
    """
    cfg = _get_config()
    body_minified = json.dumps(request_body, separators=(',', ':'))
    body_hash = hashlib.sha256(body_minified.encode('utf-8')).hexdigest().lower()
    string_to_sign = f"{http_method}:{endpoint}:{access_token}:{body_hash}:{timestamp}"
    
    sig = hmac.new(
        cfg['secret_key'].encode('utf-8'),
        string_to_sign.encode('utf-8'),
        hashlib.sha512
    ).digest()
    return base64.b64encode(sig).decode('utf-8')


# ─── Get B2B Token ───────────────────────────────────────────────────

def _get_b2b_token(force=False) -> str:
    """Get or refresh B2B access token. Cached for 15 min (900s)."""
    global _token_cache
    
    with _token_lock:  # BUG-6 FIX: prevent concurrent token refresh
        if not force and _token_cache['access_token'] and time.time() < _token_cache['expires_at']:
            return _token_cache['access_token']
    
        cfg = _get_config()
        ts = _timestamp()
        signature = _asymmetric_signature(cfg['client_id'], ts)
        
        url = f"{cfg['base_url']}/authorization/v1/access-token/b2b"
        headers = {
            'X-CLIENT-KEY': cfg['client_id'],
            'X-TIMESTAMP': ts,
            'X-SIGNATURE': signature,
            'Content-Type': 'application/json',
        }
        body = {'grantType': 'client_credentials'}
        
        resp = requests.post(url, headers=headers, json=body, timeout=30)
        data = resp.json()
        
        # Log response without sensitive token data
        safe_data = {k: v for k, v in data.items() if k != 'accessToken'}
        current_app.logger.info(f'DOKU Get Token response: {json.dumps(safe_data)}')
        
        if data.get('responseCode') != '2007300':
            raise ValueError(f"DOKU Get Token failed: {data.get('responseMessage', 'Unknown error')} (code={data.get('responseCode')})")
        
        access_token = data['accessToken']
        expires_in = int(data.get('expiresIn', 900))
        
        _token_cache['access_token'] = access_token
        _token_cache['expires_at'] = time.time() + expires_in - 60  # refresh 60s before expiry
        
        return access_token


# ─── DOKU API Request Helper ─────────────────────────────────────────

def _doku_request(endpoint: str, body: dict, method: str = 'POST') -> dict:
    """Make authenticated DOKU SNAP request with symmetric signature."""
    cfg = _get_config()
    access_token = _get_b2b_token()
    ts = _timestamp()
    
    signature = _symmetric_signature(method, endpoint, access_token, body, ts)
    
    url = f"{cfg['base_url']}{endpoint}"
    headers = {
        'X-PARTNER-ID': cfg['client_id'],
        'X-EXTERNAL-ID': _external_id(),
        'X-TIMESTAMP': ts,
        'X-SIGNATURE': signature,
        'Authorization': f'Bearer {access_token}',
        'CHANNEL-ID': 'H2H',
        'Content-Type': 'application/json',
    }
    
    current_app.logger.info(f'DOKU request: {method} {endpoint}')
    resp = requests.request(method, url, headers=headers, json=body, timeout=30)
    data = resp.json()
    current_app.logger.info(f'DOKU response: {json.dumps(data)}')
    
    return data


# ─── Generate QRIS ───────────────────────────────────────────────────

@doku_bp.route('/generate', methods=['POST'])
@jwt_required()
def generate_qris():
    """
    Generate DOKU QRIS Dynamic (SNAP QR MPM).
    Request: { "amount": 5000 }
    """
    try:
        data = request.get_json() or {}
        amount = int(data.get('amount', 0))

        cfg = _get_config()
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        # BUG-5 FIX: removed duplicate request.get_json() parse — reuse 'data' and 'amount' from above

        if amount not in TOKEN_PACKAGES:
            return jsonify({'error': 'Invalid token package amount'}), 400

        tokens = TOKEN_PACKAGES[amount]
        reference_id = f"PF-DK-{user_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

        # ── Free trial: no QRIS, credit immediately ──
        if amount == 0:
            # Check if user already claimed trial
            existing_trial = Payment.query.filter_by(
                user_id=user_id, provider='doku', amount=0, status='paid'
            ).with_for_update().first()
            if existing_trial:
                return jsonify({'error': 'Free trial already claimed'}), 400

            from sqlalchemy import text
            db.session.execute(
                text("UPDATE users SET token_quota_monthly = COALESCE(token_quota_monthly, 0) + :tokens WHERE id = :uid"),
                {"tokens": tokens, "uid": user_id}
            )
            payment = Payment(
                external_id=reference_id,
                provider='doku',
                payment_method='QRIS',
                status='paid',
                amount=0,
                tokens=tokens,
                user_id=user_id,
                raw_response='{"type":"trial"}',
            )
            db.session.add(payment)
            safe_commit()
            current_app.logger.info(f'DOKU TRIAL TOKEN: user={user_id}, tokens=+{tokens}')
            return jsonify({
                'qr_string': '',
                'amount': 0,
                'tokens': tokens,
                'transaction_id': reference_id,
                'expires_at': '',
                'provider': 'doku',
                'trial': True,
                'status': 'paid',
            })

        # QRIS validity: 10 minutes
        validity = (datetime.now(timezone(timedelta(hours=7))) + timedelta(minutes=10)).strftime('%Y-%m-%dT%H:%M:%S+07:00')

        body = {
            'partnerReferenceNo': reference_id,
            'amount': {
                'value': f"{amount}.00",
                'currency': 'IDR',
            },
            'merchantId': cfg['merchant_id'],
            'terminalId': cfg['terminal_id'],
            'validityPeriod': validity,
            'additionalInfo': {
                'postalCode': cfg['postal_code'],
                'feeType': '1',  # No Tips
            },
        }

        result = _doku_request('/snap-adapter/b2b/v1.0/qr/qr-mpm-generate', body)

        if result.get('responseCode') != '2004700':
            return jsonify({
                'error': 'Failed to generate QRIS',
                'message': result.get('responseMessage', 'Unknown'),
                'code': result.get('responseCode', ''),
                'raw': result,
            }), 502

        qr_content = result.get('qrContent', '')
        reference_no = result.get('referenceNo', reference_id)

        # Store payment record
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        payment = Payment(
            external_id=reference_no,
            provider='doku',
            payment_method='QRIS',
            status='pending',
            amount=amount,
            tokens=tokens,
            user_id=user_id,
            payment_url=qr_content,
            expires_at=expires_at,
            raw_response=json.dumps(result),
        )
        db.session.add(payment)
        safe_commit()

        return jsonify({
            'qr_string': qr_content,
            'amount': amount,
            'tokens': tokens,
            'transaction_id': reference_no,
            'reference_no': result.get('referenceNo', ''),
            'expires_at': expires_at.isoformat().replace('+00:00', 'Z'),
            'provider': 'doku',
        })

    except ValueError as e:
        current_app.logger.error(f'DOKU generate error: {e}')
        return jsonify({'error': str(e)}), 500
    except requests.RequestException as e:
        current_app.logger.error(f'DOKU network error: {e}')
        return jsonify({'error': 'DOKU gateway unreachable'}), 502
    except Exception:
        current_app.logger.exception('DOKU QRIS generation failed')
        return jsonify({'error': 'Internal server error'}), 500


# ─── Query QRIS ──────────────────────────────────────────────────────

@doku_bp.route('/query', methods=['POST'])
@jwt_required()
def query_qris():
    """
    Check QRIS payment status.
    Request: { "transaction_id": "PF-DOKU-..." }
    """
    try:
        cfg = _get_config()
        data = request.get_json() or {}
        ref = data.get('transaction_id', '')

        if not ref:
            return jsonify({'error': 'transaction_id required'}), 400

        # IDOR guard: only owner can query (read-only, no row lock to avoid deadlock with callback)
        payment = Payment.query.filter_by(external_id=ref).first()
        if not payment or str(payment.user_id) != str(get_jwt_identity()):
            return jsonify({'error': 'Not found'}), 404

        body = {
            'originalReferenceNo': ref,
            'originalPartnerReferenceNo': ref,
            'serviceCode': '47',
            'merchantId': cfg['merchant_id'],
        }

        result = _doku_request('/snap-adapter/b2b/v1.0/qr/qr-mpm-query', body)

        status = result.get('latestTransactionStatus', '')
        status_desc = result.get('transactionStatusDesc', '')

        # Map DOKU QRIS status → our status
        # '00'=paid  '01'=in-progress  '03'=pending  '05'=canceled  '07'=pending  '09'=pending  '68'=expired
        mapping = {
            '00': 'paid',
            '01': 'pending',
            '03': 'pending',
            '05': 'cancelled',
            '07': 'pending',
            '09': 'pending',
            '68': 'expired',
        }
        payment_status = mapping.get(status, 'pending')
        if status not in mapping:
            current_app.logger.warning(f'DOKU query unknown status={status} for ref={ref}, treating as pending')

        # Sync DB to DOKU's actual status (credit or settle final status)
        if payment and payment.status != payment_status:
            if payment_status == 'paid' and payment.status == 'pending':
                # Credit token
                try:
                    from sqlalchemy import text
                    db.session.execute(
                        text("UPDATE users SET token_quota_monthly = COALESCE(token_quota_monthly, 0) + :tokens WHERE id = :uid"),
                        {"tokens": payment.tokens, "uid": payment.user_id}
                    )
                    payment.status = 'paid'
                    payment.raw_response = json.dumps(result)
                    current_app.logger.info(f'DOKU QRIS TOKEN CREDITED (query): user={payment.user_id}, tokens=+{payment.tokens}, ref={ref}')
                    
                    # Upgrade user badge based on amount
                    from config.badge_tiers import upgrade_user_badge
                    user = User.query.get(payment.user_id)
                    if user:
                        upgrade_user_badge(user, payment.amount)
                        current_app.logger.info(f'DOKU badge upgraded (query): user={user.id}, badge={user.badge}')
                    
                    safe_commit()
                except Exception:
                    current_app.logger.exception('Failed to credit token on query')

        return jsonify({
            'status': payment_status,
            'amount': int(float(result.get('amount', {}).get('value', 0))) if result.get('amount') else 0,
            'reference_id': ref,
            'raw': result,
        })

    except Exception:
        current_app.logger.exception('DOKU QRIS query failed')
        return jsonify({'status': 'error', 'message': 'Internal server error'}), 500


@doku_bp.route('/query-qris-dynamic', methods=['POST'])
@jwt_required()
def query_qris_dynamic():
    """Alias for /query - frontend expects this endpoint name."""
    return query_qris()


# ─── Callback (Notification from DOKU) ───────────────────────────────

def _verify_snap_signature(headers: dict, body: dict) -> bool:
    """Verify SNAP callback signature using HMAC-SHA512.
    
    SEC-1 FIX: Previously returned True unconditionally.
    Now verifies X-SIGNATURE using the same symmetric signature algorithm
    as _symmetric_signature(), matching DOKU SNAP spec.
    Falls back to partner-ID validation if signature header is missing.
    """
    cfg = _get_config()
    secret_key = cfg.get('secret_key', '')
    client_id = cfg.get('client_id', '')
    
    if not secret_key:
        current_app.logger.error('DOKU_SECRET_KEY not configured — callback REJECTED')
        return False
    
    # Validate X-PARTNER-ID matches our client ID
    partner_id = headers.get('X-Partner-Id', headers.get('X-PARTNER-ID', ''))
    if partner_id and partner_id != client_id:
        current_app.logger.warning(f'DOKU callback: X-PARTNER-ID mismatch: got={partner_id}, expected={client_id}')
        return False
    
    # Verify HMAC-SHA512 signature if present
    signature = headers.get('X-Signature', headers.get('X-SIGNATURE', ''))
    timestamp = headers.get('X-Timestamp', headers.get('X-TIMESTAMP', ''))
    
    if signature and timestamp:
        # SNAP symmetric signature: HMAC_SHA512(secretKey, "POST:endpoint:token:sha256(body):timestamp")
        body_minified = json.dumps(body, separators=(',', ':'))
        body_hash = hashlib.sha256(body_minified.encode('utf-8')).hexdigest().lower()
        # Callback endpoint path
        endpoint = '/snap-adapter/b2b/v1.0/qr/qr-mpm-notify'
        # Token from callback header (not our cached token)
        access_token = headers.get('Authorization', '').removeprefix('Bearer ').strip()
        string_to_sign = f"POST:{endpoint}:{access_token}:{body_hash}:{timestamp}"
        
        expected_sig = base64.b64encode(
            hmac.new(
                secret_key.encode('utf-8'),
                string_to_sign.encode('utf-8'),
                hashlib.sha512
            ).digest()
        ).decode('utf-8')
        
        if not hmac.compare_digest(signature, expected_sig):
            current_app.logger.warning(f'DOKU SNAP callback: signature mismatch for body hash={body_hash[:16]}...')
            return False
        
        current_app.logger.info('DOKU SNAP callback: signature verified OK')
        return True
    
    # No signature header — reject unless partner ID matched
    if partner_id == client_id:
        current_app.logger.warning('DOKU SNAP callback: no X-SIGNATURE, accepted via X-PARTNER-ID match')
        return True
    
    current_app.logger.warning('DOKU SNAP callback: no signature and no partner ID — REJECTED')
    return False


@doku_bp.route('/callback', methods=['POST'])
def doku_callback():
    """
    Handle DOKU payment notification (DOKU native + legacy + SNAP QRIS).
    DOKU native: JSON body with order{} + transaction{} fields (e.g. {"order":{"amount":1000},"transaction":{"status":"SUCCESS"}}).
    Legacy: query params with WORDS SHA1 signature.
    SNAP QRIS: JSON body with X-SIGNATURE, X-TIMESTAMP, X-PARTNER-ID, X-EXTERNAL-ID, CHANNEL-ID.
    Must return HTTP 200 with body "CONTINUE".
    """
    # Detect format
    body = request.get_json(silent=True) or {}
    params = request.args.to_dict()

    current_app.logger.info(f'DOKU callback params: {json.dumps(params)}')
    current_app.logger.info(f'DOKU callback body: {json.dumps(body)}')

    is_snap = request.is_json and 'originalPartnerReferenceNo' in body
    # DOKU native format: has order{} + transaction{} + no originalPartnerReferenceNo
    is_doku_native = (
        request.is_json
        and 'order' in body
        and 'transaction' in body
        and 'originalPartnerReferenceNo' not in body
    )

    reference_id = ''
    status_code = ''
    amount_val = 0

    if is_snap:
        # ─── SNAP QRIS format ───
        if not _verify_snap_signature(dict(request.headers), body):
            return 'STOP', 403

        reference_id = body.get('originalPartnerReferenceNo', '') or body.get('originalReferenceNo', '')
        status_code = body.get('latestTransactionStatus', '')
        amount_obj = body.get('amount', {})
        amount_val = int(float(amount_obj.get('value', 0))) if amount_obj else 0

    elif is_doku_native:
        # ─── DOKU Native format (QRIS direct from DOKU dashboard/pos) ───
        order = body.get('order', {})
        txn = body.get('transaction', {})
        reference_id = order.get('invoice_number', '') or txn.get('original_request_id', '')
        amount_val = int(float(order.get('amount', 0)))
        # Map DOKU native status → our code
        # SUCCESS = paid (00), PENDING = pending (03), FAILED/EXPIRED = failed (05)
        txn_status = txn.get('status', '').upper()
        if txn_status == 'SUCCESS':
            status_code = '00'
        elif txn_status in ('PENDING', 'IN_PROGRESS'):
            status_code = '03'
        else:
            status_code = '05'  # FAILED, EXPIRED, CANCELLED, etc.
        current_app.logger.info(
            f'DOKU callback (native): invoice={reference_id}, amount={amount_val}, status={txn_status}→{status_code}'
        )

    else:
        # ─── Legacy format (VA, QRIS non-SNAP) ───
        doku_secret = os.getenv('DOKU_SECRET_KEY', '')
        words_received = params.get('WORDS', '')
        if doku_secret and words_received:
            amount_str = params.get('AMOUNT', '0')
            txn_id = params.get('TRANSACTIONID', '') or params.get('INVOICE', '')
            status_code_param = params.get('STATUSCODE', '')
            approve_code = params.get('APPROVALCODE', '')
            words_expected = hashlib.sha1(
                f"{amount_str}{doku_secret}{txn_id}{status_code_param}{approve_code}".encode()
            ).hexdigest()
            if not hmac.compare_digest(words_received.lower(), words_expected.lower()):
                current_app.logger.warning(f'DOKU callback: WORDS mismatch for txn={txn_id}')
                return 'STOP', 403
        elif not doku_secret:
            current_app.logger.error('DOKU_SECRET_KEY not configured — callback REJECTED')
            return 'STOP', 403

        reference_id = params.get('TRANSACTIONID', '') or params.get('INVOICE', '')
        # Legacy uses TXNSTATUS: S=Success, F=Failed
        txn_status_legacy = params.get('TXNSTATUS', '')
        status_code = '00' if txn_status_legacy == 'S' else '05'
        amount_str = params.get('AMOUNT', '0')
        amount_val = int(float(amount_str.replace(',', ''))) if amount_str else 0

    if not reference_id:
        current_app.logger.warning('DOKU callback: no reference ID found — trying QRIS Static match')

    try:
        payment = None
        if reference_id:
            payment = Payment.query.filter_by(external_id=reference_id).with_for_update().first()

        # QRIS Static fallback: no reference_id or not found → match pending QRIS_STATIC by amount
        if not payment and status_code == '00' and amount_val > 0:
            from sqlalchemy import text as sa_text
            payment = Payment.query.filter_by(
                amount=amount_val, status='pending', payment_method='QRIS_STATIC'
            ).order_by(Payment.created_at.desc()).with_for_update().first()
            if payment:
                current_app.logger.info(
                    f'DOKU callback: QRIS Static matched by amount={amount_val}, '
                    f'user={payment.user_id}, ref={payment.external_id}'
                )
            else:
                current_app.logger.warning(
                    f'DOKU callback: no payment found for ref={reference_id}, '
                    f'amount={amount_val} (QRIS Static match also failed)'
                )
                return 'CONTINUE', 200

        if not payment:
            current_app.logger.warning(f'DOKU callback: payment not found for ref={reference_id}')
            return 'CONTINUE', 200

        # Map SNAP status codes: 00=Success, 01=Initiated, 03=Pending, 05=Cancelled, 07=Pending, 09=Pending, 68=Expired
        # BUG-8 FIX: '07' and '09' are pending (not failed) — consistent with query_qris() mapping
        is_paid = status_code == '00'
        is_failed = status_code in ('05', '68')  # only truly terminal states

        if is_paid and payment.status != 'paid':
            if amount_val != payment.amount:
                current_app.logger.error(
                    f'DOKU AMOUNT MISMATCH: callback={amount_val}, expected={payment.amount}, ref={reference_id}'
                )
                return 'CONTINUE', 200

            payment.status = 'paid'
            payment.raw_response = json.dumps({'params': params, 'body': body, 'format': 'snap' if is_snap else 'legacy'})
            from sqlalchemy import text
            db.session.execute(
                text("UPDATE users SET token_quota_monthly = COALESCE(token_quota_monthly, 0) + :tokens WHERE id = :uid"),
                {"tokens": payment.tokens, "uid": payment.user_id}
            )
            current_app.logger.info(
                f'DOKU TOKEN CREDITED ({ "SNAP" if is_snap else "LEGACY" }): user={payment.user_id}, tokens=+{payment.tokens}, ref={reference_id}'
            )
            
            # Upgrade user badge based on new token quota
            from config.badge_tiers import upgrade_user_badge
            user = User.query.get(payment.user_id)
            if user:
                upgrade_user_badge(user, payment.amount)
                current_app.logger.info(f'DOKU badge upgraded: user={user.id}, badge={user.badge}')
            
            safe_commit()

        elif is_failed:
            payment.status = 'failed'
            payment.raw_response = json.dumps({'params': params, 'body': body, 'format': 'snap' if is_snap else 'legacy'})
            safe_commit()

    except Exception:
        current_app.logger.exception('DOKU callback error')

    return 'CONTINUE', 200


# ─── Generate QRIS Static ────────────────────────────────────────────

@doku_bp.route('/generate-qris-static', methods=['POST'])
@jwt_required()
def generate_qris_static():
    """
    Create a pending order for QRIS Static payment.
    No DOKU API call — just show the static QR image.
    Callback from DOKU will match by amount + user + timeframe.
    Request: { "amount": 41000 }
    """
    try:
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        data = request.get_json() or {}
        amount = int(data.get('amount', 0))

        if amount not in TOKEN_PACKAGES or amount == 0:
            return jsonify({'error': 'Invalid token package amount'}), 400

        tokens = TOKEN_PACKAGES[amount]
        reference_id = f"PF-QS-{user_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

        # Check: no duplicate pending QRIS static order for same user+amount
        existing = Payment.query.filter_by(
            user_id=user_id, amount=amount, status='pending',
            payment_method='QRIS_STATIC'
        ).first()
        if existing:
            # Expire old one
            existing.status = 'expired'
            safe_commit()

        expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        payment = Payment(
            external_id=reference_id,
            provider='doku',
            payment_method='QRIS_STATIC',
            status='pending',
            amount=amount,
            tokens=tokens,
            user_id=user_id,
            payment_url='',  # no dynamic QR
            expires_at=expires_at,
            raw_response='{"type":"qris_static"}',
        )
        db.session.add(payment)
        safe_commit()

        current_app.logger.info(f'QRIS STATIC order: user={user_id}, amount={amount}, ref={reference_id}')

        return jsonify({
            'qr_image': '/qris-static.jpeg',
            'amount': amount,
            'tokens': tokens,
            'transaction_id': reference_id,
            'expires_at': expires_at.isoformat().replace('+00:00', 'Z'),
            'provider': 'doku',
            'method': 'QRIS_STATIC',
        })

    except Exception:
        current_app.logger.exception('QRIS static generation failed')
        return jsonify({'error': 'Internal server error'}), 500


# ─── Query QRIS Static (poll by checking DB status) ─────────────────

@doku_bp.route('/query-qris-static', methods=['POST'])
@jwt_required()
def query_qris_static():
    """
    Check QRIS Static payment status — just reads DB.
    Callback from DOKU updates the status.
    Request: { "transaction_id": "PF-QS-..." }
    """
    try:
        data = request.get_json() or {}
        ref = data.get('transaction_id', '')
        if not ref:
            return jsonify({'error': 'transaction_id required'}), 400

        payment = Payment.query.filter_by(external_id=ref).first()
        if not payment or str(payment.user_id) != str(get_jwt_identity()):
            return jsonify({'error': 'Not found'}), 404

        # Check expiry
        if payment.status == 'pending' and payment.expires_at:
            if datetime.now(timezone.utc) > payment.expires_at.replace(tzinfo=timezone.utc):
                payment.status = 'expired'
                safe_commit()

        return jsonify({
            'status': payment.status,
            'amount': payment.amount,
            'tokens': payment.tokens,
        })

    except Exception:
        current_app.logger.exception('QRIS static query failed')
        return jsonify({'error': 'Internal server error'}), 500


# ─── Cancel QRIS ─────────────────────────────────────────────────────


@doku_bp.route('/generate-va', methods=['POST'])
@jwt_required()
def generate_va():
    """
    Generate DOKU Virtual Account.
    Request: { "amount": 5000, "channel": "VIRTUAL_ACCOUNT_BRI" }
    """
    try:
        cfg = _get_config()
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        data = request.get_json() or {}
        amount = int(data.get('amount', 0))

        if amount not in TOKEN_PACKAGES:
            return jsonify({'error': 'Invalid token package amount'}), 400

        tokens = TOKEN_PACKAGES[amount]
        reference_id = f"PF-DK-VA-{user_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

        # ── Free trial: no VA, credit immediately ──
        if amount == 0:
            existing_trial = Payment.query.filter_by(
                user_id=user_id, provider='doku', amount=0, status='paid'
            ).with_for_update().first()
            if existing_trial:
                return jsonify({'error': 'Free trial already claimed'}), 400

            from sqlalchemy import text
            db.session.execute(
                text("UPDATE users SET token_quota_monthly = COALESCE(token_quota_monthly, 0) + :tokens WHERE id = :uid"),
                {"tokens": tokens, "uid": user_id}
            )
            payment = Payment(
                external_id=reference_id,
                provider='doku',
                payment_method='VA',
                status='paid',
                amount=0,
                tokens=tokens,
                user_id=user_id,
                raw_response='{"type":"trial"}',
            )
            db.session.add(payment)
            safe_commit()
            current_app.logger.info(f'DOKU VA TRIAL TOKEN: user={user_id}, tokens=+{tokens}')
            return jsonify({
                'va_number': '',
                'amount': 0,
                'tokens': tokens,
                'transaction_id': reference_id,
                'expires_at': '',
                'provider': 'doku',
                'trial': True,
                'status': 'paid',
            })

        # VA expiry: 10 minutes
        validity = (datetime.now(timezone(timedelta(hours=7))) + timedelta(minutes=10)).strftime('%Y-%m-%dT%H:%M:%S+07:00')

        # Channel selection from frontend (default BRI for backward compat)
        channel = data.get('channel', 'VIRTUAL_ACCOUNT_BRI')
        valid_channels = [
            'VIRTUAL_ACCOUNT_BRI', 'VIRTUAL_ACCOUNT_BNI', 'VIRTUAL_ACCOUNT_BCA',
            'VIRTUAL_ACCOUNT_BJB', 'VIRTUAL_ACCOUNT_BNC', 'VIRTUAL_ACCOUNT_MANDIRI',
            'VIRTUAL_ACCOUNT_BANK_PERMATA',
        ]
        if channel not in valid_channels:
            channel = 'VIRTUAL_ACCOUNT_BRI'

        # DOKU VA: partnerServiceId = VA Partner Service ID, space-padded to 8 chars
        # Per-bank BIN: DOKU_VA_BIN (default/BRI), DOKU_VA_BIN_BNI, etc.
        # partnerServiceId must be exactly 8 chars (BRI: 6 digits + 2 spaces)
        va_bin_map = {
            'VIRTUAL_ACCOUNT_BNI': (os.getenv('DOKU_VA_BIN_BNI') or '').strip(),
            'VIRTUAL_ACCOUNT_BANK_PERMATA': (os.getenv('DOKU_VA_BIN_PERMATA') or '').strip(),
        }
        va_partner_id = va_bin_map.get(channel, '').strip() or (os.getenv('DOKU_VA_BIN') or '').strip()
        if not va_partner_id:
            current_app.logger.error('DOKU_VA_BIN not configured in .env')
            return jsonify({'error': 'VA not configured. Contact support.'}), 500
        # DOKU SNAP partnerServiceId is 8 chars; dashboard Merchant BIN may be 9 chars.
        # Use the dashboard Partner Service ID convention: first 8 digits of Merchant BIN.
        if len(va_partner_id) > 8:
            va_partner_id = va_partner_id[:8]
        partner_service_id = va_partner_id.rjust(8, ' ')  # SPACE-pad legacy short BINs

        current_app.logger.info(
            'DOKU VA generate: channel=%s raw_bin=%s partnerServiceId=%r len=%s',
            channel, va_partner_id, partner_service_id, len(partner_service_id)
        )

        # DGPC: customerNo = short prefix, DOKU pads it
        customer_no = str(user_id)

        # VA number = partnerServiceId (space-padded) + customerNo
        va_no = f"{partner_service_id}{customer_no}"

        body = {
            'partnerServiceId': partner_service_id,
            'customerNo': customer_no,
            'virtualAccountNo': va_no,
            'virtualAccountName': user.name or user.email,
            'virtualAccountEmail': user.email,
            'virtualAccountPhone': '',
            'trxId': reference_id,
            'totalAmount': {
                'value': f"{amount}.00",
                'currency': 'IDR',
            },
            'additionalInfo': {
                'channel': channel,
                # Closed payment (C) already locks the amount - min/max not allowed
            },
            'virtualAccountTrxType': 'C',  # Closed Amount
            'expiredDate': validity,
            'freeText': [
                {
                    'english': 'PaperFull token purchase',
                    'indonesia': 'Pembelian token PaperFull',
                }
            ],
        }

        result = _doku_request('/virtual-accounts/bi-snap-va/v1.1/transfer-va/create-va', body)

        if result.get('responseCode') != '2002700':
            return jsonify({
                'error': 'Failed to generate VA',
                'message': result.get('responseMessage', 'Unknown'),
                'code': result.get('responseCode', ''),
                'raw': result,
            }), 502

        va_data = result.get('virtualAccountData', {})
        # DOKU does not always echo channel; persist requested channel for cancel/delete-va.
        va_data.setdefault('additionalInfo', {})['channel'] = channel
        # Use DOKU's returned VA number (they pad customerNo for DGPC)
        va_number = va_data.get('virtualAccountNo', va_no)
        doku_customer_no = va_data.get('customerNo', customer_no)
        how_to_pay_page = va_data.get('additionalInfo', {}).get('howToPayPage', '')
        how_to_pay_api = va_data.get('additionalInfo', {}).get('howToPayApi', '')

        # Store payment record
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        payment = Payment(
            external_id=reference_id,
            provider='doku',
            payment_method='VA',
            status='pending',
            amount=amount,
            tokens=tokens,
            user_id=user_id,
            payment_url=va_number,  # store DOKU's VA number
            expires_at=expires_at,
            raw_response=json.dumps(result),
        )
        db.session.add(payment)
        safe_commit()

        # Map channel to bank name
        channel_map = {
            'VIRTUAL_ACCOUNT_BRI': 'BRI',
            'VIRTUAL_ACCOUNT_BNI': 'BNI',
            'VIRTUAL_ACCOUNT_BCA': 'BCA',
            'VIRTUAL_ACCOUNT_BJB': 'BJB',
            'VIRTUAL_ACCOUNT_BNC': 'BNC',
            'VIRTUAL_ACCOUNT_MANDIRI': 'Mandiri',
            'VIRTUAL_ACCOUNT_BANK_PERMATA': 'Permata',
        }
        bank_name = channel_map.get(body['additionalInfo']['channel'], 'BRI')

        return jsonify({
            'va_number': va_number,
            'amount': amount,
            'tokens': tokens,
            'transaction_id': reference_id,
            'expires_at': expires_at.isoformat().replace('+00:00', 'Z'),
            'provider': 'doku',
            'how_to_pay_page': how_to_pay_page,
            'how_to_pay_api': how_to_pay_api,
            'channel': body['additionalInfo']['channel'],
            'bank_name': bank_name,
        })

    except ValueError as e:
        current_app.logger.error(f'DOKU VA generate error: {e}')
        return jsonify({'error': str(e)}), 500
    except requests.RequestException as e:
        current_app.logger.error(f'DOKU network error: {e}')
        return jsonify({'error': 'DOKU gateway unreachable'}), 502
    except Exception:
        current_app.logger.exception('DOKU VA generation failed')
        return jsonify({'error': 'Internal server error'}), 500


# ─── Query VA ────────────────────────────────────────────────────────


@doku_bp.route('/query-va', methods=['POST'])
@jwt_required()
def query_va():
    """
    Check VA payment status.
    Request: { "transaction_id": "PF-DOKU-VA-..." }
    """
    try:
        cfg = _get_config()
        data = request.get_json() or {}
        ref = data.get('transaction_id', '')

        if not ref:
            return jsonify({'error': 'transaction_id required'}), 400

        # IDOR guard: only owner can query
        payment = Payment.query.filter_by(external_id=ref).with_for_update().first()
        if not payment or str(payment.user_id) != str(get_jwt_identity()):
            return jsonify({'error': 'Not found'}), 404

        # VA status check uses DOKU orders endpoint
        va_partner_id = (os.getenv('DOKU_VA_BIN') or '').strip()
        if not va_partner_id:
            return jsonify({'error': 'VA not configured'}), 500
        partner_service_id = va_partner_id.rjust(8, ' ')

        # Extract DOKU's padded customerNo from stored raw_response
        doku_customer_no = str(payment.user_id)
        try:
            raw = json.loads(payment.raw_response) if payment.raw_response else {}
            va_data_raw = raw.get('virtualAccountData', {})
            doku_customer_no = va_data_raw.get('customerNo', doku_customer_no)
        except (json.JSONDecodeError, AttributeError):
            pass

        body = {
            'partnerServiceId': partner_service_id,
            'customerNo': doku_customer_no,
            'virtualAccountNo': payment.payment_url,  # stored VA number (DOKU's)
            'trxId': ref,
        }

        # Check status endpoint - DOKU docs: /orders/v1.0/transfer-va/status
        result = _doku_request('/orders/v1.0/transfer-va/status', body)

        # Validate DOKU responseCode first
        # 2002600=success, 4032600=expired (still valid final state we should process)
        response_code = result.get('responseCode', '')
        if response_code not in ('2002600', '4032600'):
            current_app.logger.warning(f'DOKU VA query error: responseCode={response_code}, message={result.get("responseMessage")}')
            return jsonify({
                'status': payment.status,
                'error': result.get('responseMessage', 'Query failed'),
                'code': response_code,
            }), 502

        va_data = result.get('virtualAccountData') or {}
        status = result.get('latestTransactionStatus', '') or result.get('virtualAccountTrxStatus', '')
        status_desc = result.get('transactionStatusDesc', '')
        flag_reason = va_data.get('paymentFlagReason') or {}
        flag_text = (flag_reason.get('english') or flag_reason.get('indonesia') or '').lower()

        # Map DOKU VA status → our status.
        # DOKU VA status endpoint often omits latestTransactionStatus while returning
        # paymentFlagReason=Pending; empty status must stay pending, not failed.
        # responseCode 4032600 + paymentFlagReason=Expired -> expired
        payment_status = 'pending'
        if response_code == '4032600' and ('expired' in flag_text or 'kadaluarsa' in flag_text):
            payment_status = 'expired'
        elif status == '00' or 'paid' in flag_text or 'success' in flag_text or 'sukses' in flag_text or 'terbayar' in flag_text:
            payment_status = 'paid'
        elif status in ('', '01', '02') or 'pending' in flag_text or 'belum terbayar' in flag_text:
            payment_status = 'pending'
        else:
            payment_status = 'failed'

        # Reconciliation: sync DB to DOKU's actual status
        if payment_status == 'paid' and payment and payment.status != 'paid':
            paid_amount_raw = (va_data.get('paidAmount') or {}).get('value', '0')
            try:
                paid_amount = int(float(str(paid_amount_raw).replace(',', '')))
            except (ValueError, TypeError):
                paid_amount = 0

            if paid_amount != payment.amount:
                current_app.logger.error(
                    f'DOKU VA AMOUNT MISMATCH: paid={paid_amount}, expected={payment.amount}, ref={ref}'
                )
                payment.status = 'failed'
                payment.raw_response = json.dumps(result)
                safe_commit()
            else:
                try:
                    from sqlalchemy import text
                    db.session.execute(
                        text("UPDATE users SET token_quota_monthly = COALESCE(token_quota_monthly, 0) + :tokens WHERE id = :uid"),
                        {"tokens": payment.tokens, "uid": payment.user_id}
                    )
                    payment.status = 'paid'
                    payment.raw_response = json.dumps(result)
                    db.session.commit()
                    current_app.logger.info(f'DOKU VA TOKEN CREDITED: user={payment.user_id}, tokens=+{payment.tokens}, ref={ref}')
                except Exception:
                    db.session.rollback()
                    current_app.logger.exception(f'DOKU VA credit failed for ref={ref}')
        elif payment_status in ('expired', 'failed', 'cancelled') and payment and payment.status == 'pending':
            # Settle final non-paid status
            payment.status = payment_status
            payment.raw_response = json.dumps(result)
            safe_commit()
            current_app.logger.info(f'DOKU VA query settled: ref={ref} status={payment_status}')

        return jsonify({
            'status': payment_status,
            'doku_status': status,
            'status_desc': status_desc,
            'paid_time': result.get('paidTime', ''),
            'amount': result.get('totalAmount', {}),
            'raw': result,
        })

    except Exception:
        current_app.logger.exception('DOKU VA query failed')
        return jsonify({'error': 'Internal server error'}), 500

@doku_bp.route('/cancel', methods=['POST'])
@jwt_required()
def cancel_qris():
    """
    Cancel/expire a QRIS.
    Request: { "transaction_id": "PF-DOKU-..." }
    """
    try:
        cfg = _get_config()
        data = request.get_json() or {}
        ref = data.get('transaction_id', '')

        if not ref:
            return jsonify({'error': 'transaction_id required'}), 400

        # IDOR guard: only owner can cancel
        payment = Payment.query.filter_by(external_id=ref).with_for_update().first()
        if not payment or str(payment.user_id) != str(get_jwt_identity()):
            return jsonify({'error': 'Not found'}), 404

        body = {
            'partnerReferenceNo': ref,
            'referenceNo': ref,
            'merchantId': cfg['merchant_id'],
            'reason': 'User cancelled',
        }

        result = _doku_request('/snap-adapter/b2b/v1.0/qr/qr-expire', body)

        if result.get('responseCode') == '2007700':
            # Update local payment status only after DOKU confirms cancellation
            payment.status = 'cancelled'
            safe_commit()

            return jsonify({'status': 'cancelled', 'raw': result})

        return jsonify({
            'error': 'Failed to cancel QRIS',
            'message': result.get('responseMessage', ''),
            'raw': result,
        }), 502

    except Exception:
        current_app.logger.exception('DOKU cancel failed')
        return jsonify({'error': 'Internal server error'}), 500


@doku_bp.route('/cancel-va', methods=['POST'])
@jwt_required()
def cancel_va():
    """
    Cancel VA via DOKU API (DELETE /virtual-accounts/bi-snap-va/v1.1/transfer-va/delete-va)
    Request: { "transaction_id": "PF-DK-VA-..." }
    """
    try:
        cfg = _get_config()
        data = request.get_json() or {}
        ref = data.get('transaction_id', '')

        if not ref:
            return jsonify({'error': 'transaction_id required'}), 400

        # IDOR guard: only owner can cancel
        payment = Payment.query.filter_by(external_id=ref).with_for_update().first()
        if not payment or str(payment.user_id) != str(get_jwt_identity()):
            return jsonify({'error': 'Not found'}), 404

        # Extract VA details from stored payment. Do not mark local cancelled
        # unless DOKU confirms deletion, otherwise dashboard DOKU stays pending.
        if not payment.payment_url:
            return jsonify({'error': 'Missing VA number for DOKU cancellation'}), 409

        # Parse stored VA number to get components
        # Format from DOKU: "  1392500006076800" (space-padded BIN + customerNo)
        va_number = payment.payment_url  # DO NOT strip, keep leading spaces
        if len(va_number) < 8:
            return jsonify({'error': 'Invalid VA number for DOKU cancellation'}), 409

        # Extract partnerServiceId (first 8 chars, space-padded) and customerNo (rest)
        partner_service_id = va_number[:8]  # already space-padded from storage
        customer_no = va_number[8:]  # keep leading zeros, do NOT strip

        # Get DOKU VA BIN for channel mapping (optional validation)
        va_partner_id = (os.getenv('DOKU_VA_BIN') or '').strip()
        if va_partner_id:
            # Validate that the parsed partnerServiceId matches config (ignoring spaces)
            if partner_service_id.strip() != va_partner_id:
                current_app.logger.warning(f'DOKU VA BIN mismatch: parsed={partner_service_id!r} config={va_partner_id!r}')
                # Continue anyway, as the VA number came from DOKU's own response

        # Extract channel from stored raw_response so cancel uses correct bank channel
        stored_channel = 'VIRTUAL_ACCOUNT_BRI'  # default fallback
        if payment.raw_response:
            try:
                raw = json.loads(payment.raw_response)
                stored_channel = (
                    raw.get('virtualAccountData', {})
                    .get('additionalInfo', {})
                    .get('channel', stored_channel)
                )
            except Exception:
                pass

        body = {
            'partnerServiceId': partner_service_id,
            'customerNo': customer_no,
            'virtualAccountNo': va_number,
            'additionalInfo': {'channel': stored_channel},
        }

        result = _doku_request('/virtual-accounts/bi-snap-va/v1.1/transfer-va/delete-va', body, method='DELETE')

        # DOKU returns 2003100 for successful VA deletion (not 2002500 which is for create/update)
        if result.get('responseCode') in ('2002500', '2003100'):
            # Successfully deleted via DOKU API
            payment.status = 'cancelled'
            safe_commit()
            current_app.logger.info(f'DOKU VA DELETED via API: user={payment.user_id}, ref={ref}')
            return jsonify({'status': 'cancelled', 'raw': result})

        current_app.logger.warning(f'DOKU VA delete API failed: {result.get("responseMessage")}')
        return jsonify({
            'error': 'Failed to cancel VA on DOKU',
            'message': result.get('responseMessage', ''),
            'raw': result,
        }), 502

    except Exception:
        current_app.logger.exception('DOKU VA cancel API failed')
        return jsonify({'error': 'Internal server error'}), 500


# ─── Test endpoint (sandbox only) ────────────────────────────────────

@doku_bp.route('/test-token', methods=['GET'])
def test_token():
    """Test B2B token generation — disabled in production."""
    return jsonify({'error': 'Not found'}), 404
