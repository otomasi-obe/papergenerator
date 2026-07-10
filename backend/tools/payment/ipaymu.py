"""
iPaymu payment integration for PaperFull.
Endpoints: generate (QRIS/VA), callback, status.
"""

import os
import json
import hashlib
import hmac
import uuid
import requests
from datetime import datetime, timezone, timedelta
from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from utils.database.models import db, User, Payment, safe_commit

ipaymu_bp = Blueprint('ipaymu', __name__, url_prefix='/api/payment/ipaymu')

# ─── Token package mapping ───────────────────────────────────────────
TOKEN_PACKAGES = {
    35000:   300000,   # Harian
    120000:  1200000,  # Mingguan
    300000:  3500000,  # Bulanan
}


def _get_credentials():
    api_key = os.getenv('IPAYMU_API_KEY')
    va = os.getenv('IPAYMU_VA')
    if not api_key or not va:
        raise ValueError('iPaymu credentials not configured')
    return api_key, va


def _sign_request(data: dict, api_key: str, va: str) -> str:
    """Generate HMAC-SHA256 signature for iPaymu API v2."""
    body = json.dumps(data, separators=(',', ':'))
    req_body = hashlib.sha256(body.encode()).hexdigest().lower()
    string_to_sign = f"POST:{va}:{req_body}:{api_key}".encode()
    return hmac.new(bytes(api_key, "utf-8"), string_to_sign, hashlib.sha256).hexdigest()


def _ipaymu_request(endpoint: str, data: dict) -> dict:
    """Make signed request to iPaymu API."""
    api_key, va = _get_credentials()
    signature = _sign_request(data, api_key, va)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    url = f"https://my.ipaymu.com/api/v2{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "va": va,
        "signature": signature,
        "timestamp": timestamp,
    }

    resp = requests.post(url, headers=headers, json=data, timeout=30)
    return resp.json()


@ipaymu_bp.route('/generate', methods=['POST'])
@jwt_required()
def generate_payment():
    """
    Generate iPaymu payment (redirect-based).
    Request body: { "amount": 5000, "description": "Token purchase", "method": "qris" }
    """
    try:
        api_key, va = _get_credentials()
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        data = request.get_json() or {}
        amount = int(data.get('amount', 0))
        description = data.get('description', 'PaperFull Token Purchase')
        method = data.get('method', 'qris')  # 'qris' or 'va'

        if amount not in TOKEN_PACKAGES:
            return jsonify({'error': 'Invalid token package amount'}), 400

        # Map amount → tokens. Never fallback 1:1; client amount is user-controlled.
        tokens = TOKEN_PACKAGES[amount]

        reference_id = f"PF-IP-{user_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

        payload = {
            "account": va,
            "product": [description],
            "qty": ["1"],
            "price": [str(amount)],
            "description": [description],
            "notifyUrl": "https://paperfull.app/api/payment/ipaymu/callback",
            "returnUrl": "https://paperfull.app/payment/success",
            "cancelUrl": "https://paperfull.app/payment/cancel",
            "referenceId": reference_id,
            "buyerName": user.name or "User",
            "buyerEmail": user.email or "",
            "paymentMethod": method,
            "paymentChannel": method,
            "expired": "10",
            "expiredType": "minutes",
        }

        current_app.logger.info(f'Creating iPaymu payment: amount={amount}, ref={reference_id}, method={method}')

        result = _ipaymu_request("/payment/direct", payload)

        if not result.get('Success'):
            current_app.logger.error(f'iPaymu error: {json.dumps(result)}')
            return jsonify({'error': 'Failed to generate payment', 'message': result.get('Message', 'Unknown error')}), 502

        payment_url = result.get('Data', {}).get('QrTemplate', '') or result.get('Data', {}).get('Url', '')
        qr_image = result.get('Data', {}).get('QrImage', '')
        qr_string = result.get('Data', {}).get('QrString', '')
        session_id = result.get('Data', {}).get('SessionId', '')

        # Store payment record
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        payment = Payment(
            external_id=reference_id,
            provider='ipaymu',
            status='pending',
            amount=amount,
            tokens=tokens,
            user_id=user_id,
            payment_url=payment_url,
            expires_at=expires_at,
            raw_response=json.dumps(result),
        )
        db.session.add(payment)
        safe_commit()

        return jsonify({
            'payment_url': payment_url,
            'qr_image': qr_image,
            'qr_string': qr_string,
            'session_id': session_id,
            'amount': amount,
            'tokens': tokens,
            'description': description,
            'transaction_id': reference_id,
            'expires_at': expires_at.isoformat().replace('+00:00', 'Z'),
            'method': method,
        })

    except ValueError as e:
        return jsonify({'error': str(e)}), 500
    except requests.RequestException as e:
        current_app.logger.error(f'iPaymu network error: {e}')
        return jsonify({'error': 'Payment gateway unreachable'}), 502
    except Exception:
        current_app.logger.exception('iPaymu payment generation failed')
        return jsonify({'error': 'Internal server error'}), 500


@ipaymu_bp.route('/callback', methods=['POST'])
def ipaymu_callback():
    """
    Handle iPaymu payment callback (notifyUrl).
    iPaymu sends: trx_id, reference_id, status, status_code, via, channel, amount, fee, etc.
    """
    data = request.form.to_dict() if request.content_type and 'form' in request.content_type else (request.get_json() or {})
    current_app.logger.info(f'iPaymu callback received: {json.dumps(data)}')

    # ─── Verify iPaymu signature ───
    expected_key = os.getenv('IPAYMU_API_KEY', '')
    if expected_key:
        # iPaymu callback includes 'signature' field — HMAC-SHA256 of body with API key
        sig_received = data.get('signature', '') or request.headers.get('x-ipaymu-signature', '')
        if not sig_received:
            current_app.logger.warning('iPaymu callback: missing signature')
            return jsonify({'status': 'rejected'}), 403
        # Reconstruct and verify
        # iPaymu signs: sha256(request_body) with api_key
        raw_body = request.get_data(as_text=True) or ''
        body_hash = hashlib.sha256(raw_body.encode()).hexdigest().lower()
        expected_sig = hmac.new(expected_key.encode(), body_hash.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig_received, expected_sig):
            current_app.logger.warning(f'iPaymu callback: invalid signature for ref={data.get("reference_id", "?")}')
            return jsonify({'status': 'rejected'}), 403
    else:
        current_app.logger.error('IPAYMU_API_KEY not configured — callback REJECTED')
        return jsonify({'status': 'rejected'}), 403

    try:
        reference_id = data.get('reference_id', '')
        status_code = str(data.get('status_code', ''))
        status = data.get('status', '').lower()

        payment = Payment.query.filter_by(external_id=reference_id).with_for_update().first()
        if not payment:
            return jsonify({'status': 'not_found'}), 200

        # iPaymu status_code: 1 = berhasil, 0 = pending, -1 = expired, -2 = cancelled
        if status_code == '1' or status == 'berhasil':
            if payment.status != 'paid':  # Prevent double-credit
                # Verify amount matches
                callback_amount = int(float(data.get('amount', 0)))
                if callback_amount != payment.amount:
                    current_app.logger.error(
                        f'iPaymu AMOUNT MISMATCH: callback={callback_amount}, expected={payment.amount}, ref={reference_id}'
                    )
                    return jsonify({'status': 'amount_mismatch'}), 200

                payment.status = 'paid'
                payment.raw_response = json.dumps(data)
                # ─── Atomic token credit ───
                from sqlalchemy import text
                db.session.execute(
                    text("UPDATE users SET token_quota_monthly = COALESCE(token_quota_monthly, 0) + :tokens WHERE id = :uid"),
                    {"tokens": payment.tokens, "uid": payment.user_id}
                )
                current_app.logger.info(
                    f'TOKEN CREDITED: user={payment.user_id}, tokens=+{payment.tokens}, ref={reference_id}'
                )
                safe_commit()

        elif status_code == '-1' or status == 'expired':
            payment.status = 'expired'
            safe_commit()

        elif status_code == '-2' or status == 'cancelled':
            payment.status = 'cancelled'
            safe_commit()

        return jsonify({'status': 'received'}), 200

    except Exception:
        current_app.logger.exception(f'iPaymu callback error')
        return jsonify({'status': 'error'}), 200


@ipaymu_bp.route('/status/<reference_id>', methods=['GET'])
@jwt_required()
def check_status(reference_id):
    """Check payment status from local DB."""
    try:
        user_id = int(get_jwt_identity())
        payment = Payment.query.filter_by(external_id=reference_id, user_id=user_id).first()

        if not payment:
            return jsonify({'error': 'Payment not found'}), 404

        return jsonify({
            'status': payment.status,
            'amount': payment.amount,
            'tokens': payment.tokens,
            'transaction_id': payment.external_id,
            'created_at': payment.created_at.isoformat() if payment.created_at else None,
        })

    except Exception:
        current_app.logger.exception('iPaymu status check failed')
        return jsonify({'error': 'Internal server error'}), 500
