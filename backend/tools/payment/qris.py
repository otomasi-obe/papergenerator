"""
Payment Gateway - Xendit QRIS + VA Integration
"""
import json
import os
import uuid
import base64
import httpx
from datetime import datetime, timezone, timedelta
from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from utils.database.models import db, User, Payment, safe_commit

payment_bp = Blueprint('payment', __name__, url_prefix='/api/payment')


def _get_xendit_credentials():
    """Get Xendit API key"""
    api_key = os.getenv('XENDIT_API_KEY')
    if not api_key:
        raise ValueError('XENDIT_API_KEY not configured')
    return api_key


def _verify_xendit_callback() -> bool:
    """Verify Xendit callback using x-callback-token header (timing-safe)."""
    expected = os.getenv('XENDIT_CALLBACK_TOKEN', '')
    if not expected:
        current_app.logger.error('XENDIT_CALLBACK_TOKEN not configured — rejecting callback')
        return False
    received = request.headers.get('x-callback-token', '')
    import hmac
    return hmac.compare_digest(received, expected)


@payment_bp.route('/qris/generate', methods=['POST'])
@jwt_required()
def generate_qris():
    """
    Generate QRIS payment via Xendit
    Request body: { "amount": 5000, "description": "Token purchase" }
    """
    try:
        api_key = _get_xendit_credentials()
        data = request.get_json() or {}
        amount = data.get('amount')
        description = data.get('description', 'PaperFull Token Purchase')

        if not amount or int(amount) < 1000:
            return jsonify({'error': 'Amount must be >= 1000 IDR'}), 400

        user_id = int(get_jwt_identity())
        reference_id = f"PF-QRIS-{datetime.now().strftime('%Y%m%d%H%M%S')}-{user_id}-{uuid.uuid4().hex[:8]}"
        user = User.query.get(user_id)
        email = data.get('email', user.email if user else '')

        # Map amount → tokens. Never fallback 1:1; client amount is user-controlled.
        TOKEN_PACKAGES = {1000: 10, 5000: 60, 15000: 200, 150000: 3000}
        amount = int(amount)
        if amount not in TOKEN_PACKAGES:
            return jsonify({'error': 'Invalid token package amount'}), 400
        tokens = TOKEN_PACKAGES[amount]

        payload = {
            'external_id': reference_id,
            'type': 'DYNAMIC',
            'amount': int(amount),
            'qr_description': description[:255],
            'callback_url': 'https://paperfull.app/api/payment/qris/callback',
            'redirect_url': 'https://paperfull.app/payment/success'
        }

        headers = {
            'Authorization': f'Basic {base64.b64encode(f"{api_key}:".encode()).decode()}',
            'Content-Type': 'application/json',
            'x-idempotency-key': reference_id
        }

        current_app.logger.info(f'Creating Xendit QRIS: amount={amount}, ref={reference_id}')

        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                'https://api.xendit.co/qr_codes',
                json=payload,
                headers=headers
            )

        result = response.json()

        if response.status_code >= 400:
            current_app.logger.error(f'Xendit error: {response.status_code} - {response.text}')
            return jsonify({'error': 'Failed to generate QRIS', 'details': result}), 502

        # Store payment record
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        payment = Payment(
            external_id=reference_id,
            provider='xendit_qris',
            status='pending',
            amount=int(amount),
            tokens=tokens,
            user_id=user_id,
            payment_url=result.get('qr_url', ''),
            expires_at=expires_at,
            raw_response=json.dumps(result),
        )
        db.session.add(payment)
        safe_commit()

        return jsonify({
            'payment_url': result.get('qr_url', ''),
            'qr_string': result.get('qr_string', ''),
            'amount': amount,
            'tokens': tokens,
            'description': description,
            'transaction_id': reference_id,
            'expires_at': expires_at.isoformat().replace('+00:00', 'Z'),
            'method': 'QRIS'
        })

    except ValueError as e:
        return jsonify({'error': 'Payment gateway not configured'}), 500
    except httpx.RequestError as e:
        current_app.logger.error(f'Xendit network error: {e}')
        return jsonify({'error': 'Payment gateway unreachable'}), 502
    except Exception as e:
        current_app.logger.exception('QRIS generation failed')
        return jsonify({'error': 'Internal server error'}), 500


@payment_bp.route('/qris/callback', methods=['POST'])
def qris_callback():
    """Handle Xendit QRIS callback"""
    # 1. Verify Xendit signature
    if not _verify_xendit_callback():
        current_app.logger.warning('QRIS callback rejected: invalid token')
        return jsonify({'status': 'rejected'}), 403

    data = request.get_json(silent=True) or {}
    current_app.logger.info(f'Xendit QRIS callback: {json.dumps(data)}')

    try:
        external_id = data.get('external_id', '')
        status = data.get('status', '').upper()
        amount = float(data.get('amount', 0))

        if status == 'PAID':
            current_app.logger.info(f'QRIS PAID: {external_id}, amount={amount}')
            payment = Payment.query.filter_by(external_id=external_id).with_for_update().first()
            if payment:
                if payment.status == 'paid':
                    current_app.logger.info(f'QRIS already credited: {external_id}')
                elif int(amount) != payment.amount:
                    current_app.logger.error(
                        f'QRIS AMOUNT MISMATCH: callback={int(amount)}, expected={payment.amount}, ref={external_id}'
                    )
                else:
                    payment.status = 'paid'
                    payment.raw_response = json.dumps(data)
                    from sqlalchemy import text as sa_text
                    db.session.execute(
                        sa_text("UPDATE users SET token_quota_monthly = COALESCE(token_quota_monthly, 0) + :tokens WHERE id = :uid"),
                        {"tokens": payment.tokens, "uid": payment.user_id}
                    )
                    current_app.logger.info(
                        f'TOKEN CREDITED: user={payment.user_id}, tokens=+{payment.tokens}, ref={external_id}'
                    )
                    safe_commit()
        elif status == 'EXPIRED':
            current_app.logger.info(f'QRIS EXPIRED: {external_id}')
            payment = Payment.query.filter_by(external_id=external_id).with_for_update().first()
            if payment:
                payment.status = 'expired'
                safe_commit()
        elif status == 'FAILED':
            current_app.logger.error(f'QRIS FAILED: {external_id}')
            payment = Payment.query.filter_by(external_id=external_id).with_for_update().first()
            if payment:
                payment.status = 'failed'
                safe_commit()

        return jsonify({'status': 'received'}), 200
    except Exception as e:
        current_app.logger.exception(f'Callback error: {e}')
        return jsonify({'status': 'error'}), 200


@payment_bp.route('/qris/status/<external_id>', methods=['GET'])
@jwt_required()
def check_qris_status(external_id):
    """Check QRIS payment status"""
    try:
        # IDOR guard: only owner can check status
        payment = Payment.query.filter_by(external_id=external_id).first()
        if not payment or str(payment.user_id) != str(get_jwt_identity()):
            return jsonify({'error': 'Not found'}), 404

        api_key = _get_xendit_credentials()
        headers = {
            'Authorization': f'Basic {base64.b64encode(f"{api_key}:".encode()).decode()}'
        }

        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f'https://api.xendit.co/qr_codes/{external_id}',
                headers=headers
            )

        if response.status_code >= 400:
            return jsonify({'error': 'Failed to check status'}), 502

        result = response.json()
        return jsonify({
            'external_id': external_id,
            'status': result.get('status', ''),
            'paid': result.get('status', '').upper() == 'PAID',
            'amount': result.get('amount'),
            'data': result
        })

    except Exception as e:
        current_app.logger.exception('QRIS status check failed')
        return jsonify({'error': 'Internal server error'}), 500


# ============================================
# Virtual Account (VA) Payment Endpoints
# ============================================
SUPPORTED_VA_BANKS = {
    'bca': {'name': 'Bank BCA', 'code': 'BCA', 'icon': 'bca'},
    'bni': {'name': 'Bank BNI', 'code': 'BNI', 'icon': 'bni'},
    'bri': {'name': 'Bank BRI', 'code': 'BRI', 'icon': 'bri'},
    'mandiri': {'name': 'Bank Mandiri', 'code': 'MANDIRI', 'icon': 'mandiri'},
    'cimb': {'name': 'CIMB Niaga', 'code': 'CIMB', 'icon': 'cimb'},
    'permata': {'name': 'Bank Permata', 'code': 'PERMATA', 'icon': 'permata'},
}


@payment_bp.route('/va/generate', methods=['POST'])
@jwt_required()
def generate_va():
    """
    Generate Virtual Account payment via Xendit
    Request body: { "amount": 5000, "bank": "bca", "description": "Token purchase" }
    """
    try:
        api_key = _get_xendit_credentials()
        data = request.get_json() or {}
        amount = data.get('amount')
        bank = data.get('bank', 'bca').lower()
        description = data.get('description', 'PaperFull Token Purchase')

        if not amount:
            return jsonify({'error': 'Amount is required'}), 400
        amount = int(amount)
        TOKEN_PACKAGES = {1000: 10, 5000: 60, 15000: 200, 150000: 3000}
        if amount not in TOKEN_PACKAGES:
            return jsonify({'error': 'Invalid token package amount'}), 400

        if bank not in SUPPORTED_VA_BANKS:
            return jsonify({
                'error': 'Unsupported bank',
                'supported_banks': list(SUPPORTED_VA_BANKS.keys())
            }), 400

        user_id = int(get_jwt_identity())
        reference_id = f"PF-VA-{datetime.now().strftime('%Y%m%d%H%M%S')}-{user_id}-{uuid.uuid4().hex[:8]}"
        user = User.query.get(user_id)
        user_email = data.get('email', user.email if user else '')
        user_name = data.get('name', user.name if user else 'Customer')

        bank_code = SUPPORTED_VA_BANKS[bank]['code']

        payload = {
            'external_id': reference_id,
            'bank_code': bank_code,
            'name': user_name[:50],
            'expected_amount': int(amount),
            'expiration_date': (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
            'is_closed': True,
            'min_amount': int(amount),
            'max_amount': int(amount)
        }

        if user_email:
            payload['email_notification'] = True
            payload['customer_notification_preference'] = {
                'invoice_created': ['email'],
                'invoice_reminder': ['email'],
                'invoice_paid': ['email']
            }

        headers = {
            'Authorization': f'Basic {base64.b64encode(f"{api_key}:".encode()).decode()}',
            'Content-Type': 'application/json',
            'x-idempotency-key': reference_id
        }

        current_app.logger.info(f'Creating Xendit VA: bank={bank}, amount={amount}, ref={reference_id}')

        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                'https://api.xendit.co/callback_virtual_accounts',
                json=payload,
                headers=headers
            )

        result = response.json()

        if response.status_code >= 400:
            current_app.logger.error(f'Xendit VA error: {response.status_code} - {response.text}')
            return jsonify({'error': 'Failed to generate VA', 'details': result}), 502

        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

        # Store payment record
        TOKEN_PACKAGES = {1000: 10, 5000: 60, 15000: 200, 150000: 3000}
        tokens = TOKEN_PACKAGES.get(int(amount))
        if tokens is None:
            return jsonify({'error': 'Invalid token package amount'}), 400
        payment = Payment(
            external_id=reference_id,
            provider='xendit_va',
            status='pending',
            amount=int(amount),
            tokens=tokens,
            user_id=user_id,
            payment_url=result.get('invoice_url', ''),
            expires_at=expires_at,
            raw_response=json.dumps(result),
        )
        db.session.add(payment)
        safe_commit()

        return jsonify({
            'payment_url': result.get('invoice_url', ''),
            'account_number': result.get('account_number', ''),
            'bank_code': bank_code,
            'bank_name': SUPPORTED_VA_BANKS[bank]['name'],
            'amount': amount,
            'tokens': tokens,
            'description': description,
            'transaction_id': reference_id,
            'expires_at': expires_at.isoformat().replace('+00:00', 'Z'),
            'method': 'VA',
            'bank': bank
        })

    except ValueError as e:
        return jsonify({'error': 'Payment gateway not configured'}), 500
    except httpx.RequestError as e:
        current_app.logger.error(f'Xendit network error: {e}')
        return jsonify({'error': 'Payment gateway unreachable'}), 502
    except Exception as e:
        current_app.logger.exception('VA generation failed')
        return jsonify({'error': 'Internal server error'}), 500


@payment_bp.route('/va/callback', methods=['POST'])
def va_callback():
    """Handle Xendit VA callback"""
    if not _verify_xendit_callback():
        current_app.logger.warning('VA callback rejected: invalid token')
        return jsonify({'status': 'rejected'}), 403

    data = request.get_json(silent=True) or {}
    current_app.logger.info(f'Xendit VA callback: {json.dumps(data)}')

    try:
        external_id = data.get('external_id', '')
        status = data.get('status', '').upper()
        amount = float(data.get('expected_amount', 0))

        if status == 'PAID':
            current_app.logger.info(f'VA PAID: {external_id}, amount={amount}')
            payment = Payment.query.filter_by(external_id=external_id).with_for_update().first()
            if payment:
                if payment.status == 'paid':
                    current_app.logger.info(f'VA already credited: {external_id}')
                elif int(amount) != payment.amount:
                    current_app.logger.error(
                        f'VA AMOUNT MISMATCH: callback={int(amount)}, expected={payment.amount}, ref={external_id}'
                    )
                else:
                    payment.status = 'paid'
                    payment.raw_response = json.dumps(data)
                    from sqlalchemy import text as sa_text
                    db.session.execute(
                        sa_text("UPDATE users SET token_quota_monthly = COALESCE(token_quota_monthly, 0) + :tokens WHERE id = :uid"),
                        {"tokens": payment.tokens, "uid": payment.user_id}
                    )
                    current_app.logger.info(
                        f'TOKEN CREDITED: user={payment.user_id}, tokens=+{payment.tokens}, ref={external_id}'
                    )
                    safe_commit()
        elif status == 'EXPIRED':
            current_app.logger.info(f'VA EXPIRED: {external_id}')
            payment = Payment.query.filter_by(external_id=external_id).with_for_update().first()
            if payment:
                payment.status = 'expired'
                safe_commit()
        elif status == 'FAILED':
            current_app.logger.error(f'VA FAILED: {external_id}')
            payment = Payment.query.filter_by(external_id=external_id).with_for_update().first()
            if payment:
                payment.status = 'failed'
                safe_commit()

        return jsonify({'status': 'received'}), 200
    except Exception as e:
        current_app.logger.exception(f'VA callback error: {e}')
        return jsonify({'status': 'error'}), 200


@payment_bp.route('/va/status/<external_id>', methods=['GET'])
@jwt_required()
def check_va_status(external_id):
    """Check VA payment status"""
    try:
        # IDOR guard: only owner can check status
        payment = Payment.query.filter_by(external_id=external_id).first()
        if not payment or str(payment.user_id) != str(get_jwt_identity()):
            return jsonify({'error': 'Not found'}), 404

        api_key = _get_xendit_credentials()
        headers = {
            'Authorization': f'Basic {base64.b64encode(f"{api_key}:".encode()).decode()}'
        }

        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f'https://api.xendit.co/callback_virtual_accounts/external_id={external_id}',
                headers=headers
            )

        if response.status_code >= 400:
            return jsonify({'error': 'Failed to check status'}), 502

        result = response.json()
        return jsonify({
            'external_id': external_id,
            'status': result.get('status', ''),
            'paid': result.get('status', '').upper() == 'PAID',
            'data': result
        })

    except Exception as e:
        current_app.logger.exception('VA status check failed')
        return jsonify({'error': 'Internal server error'}), 500


@payment_bp.route('/methods', methods=['GET'])
def get_payment_methods():
    """Get available payment methods"""
    return jsonify({
        'qris': {
            'name': 'QRIS',
            'description': 'Scan QR code dengan aplikasi bank/e-wallet',
            'min_amount': 1000,
            'icon': 'qris'
        },
        'va': {
            'name': 'Virtual Account',
            'description': 'Transfer ke rekening virtual account',
            'min_amount': 1000,
            'banks': [
                {'code': 'bca', 'name': 'Bank BCA', 'icon': 'bca'},
                {'code': 'bni', 'name': 'Bank BNI', 'icon': 'bni'},
                {'code': 'bri', 'name': 'Bank BRI', 'icon': 'bri'},
                {'code': 'mandiri', 'name': 'Bank Mandiri', 'icon': 'mandiri'},
                {'code': 'cimb', 'name': 'CIMB Niaga', 'icon': 'cimb'},
                {'code': 'permata', 'name': 'Bank Permata', 'icon': 'permata'},
            ],
            'icon': 'va'
        }
    })
