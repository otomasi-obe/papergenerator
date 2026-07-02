"""
Payment Gateway - Xendit QRIS + VA Integration
"""
import os
import json
import base64
import httpx
from datetime import datetime, timezone, timedelta
from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

payment_bp = Blueprint('payment', __name__, url_prefix='/api/payment')


def _get_xendit_credentials():
    """Get Xendit API key"""
    api_key = os.getenv('XENDIT_API_KEY')
    if not api_key:
        raise ValueError('XENDIT_API_KEY not configured')
    return api_key


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

        reference_id = f"PF-{datetime.now().strftime('%Y%m%d%H%M%S')}-{amount}"
        user_id = get_jwt_identity()
        email = data.get('email', '')

        payload = {
            'external_id': reference_id,
            'type': 'DYNAMIC',
            'amount': int(amount),
            'qr_description': description[:255],
            'callback_url': f'{request.host_url.rstrip("/")}/api/payment/qris/callback',
            'redirect_url': f'{request.host_url.rstrip("/")}/payment/success'
        }

        headers = {
            'Authorization': f'Basic {base64.b64encode(api_key.encode()).decode()}',
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

        # QRIS expires in 10 minutes
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

        return jsonify({
            'payment_url': result.get('qr_url', ''),
            'qr_string': result.get('qr_string', ''),
            'amount': amount,
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
    data = request.json
    current_app.logger.info(f'Xendit QRIS callback: {json.dumps(data)}')

    try:
        external_id = data.get('external_id', '')
        status = data.get('status', '').upper()
        amount = float(data.get('amount', 0))

        if status == 'PAID':
            current_app.logger.info(f'QRIS PAID: {external_id}, amount={amount}')
            # TODO: Update user token balance
        elif status == 'EXPIRED':
            current_app.logger.info(f'QRIS EXPIRED: {external_id}')
        elif status == 'FAILED':
            current_app.logger.error(f'QRIS FAILED: {external_id}')

        return jsonify({'status': 'received'}), 200
    except Exception as e:
        current_app.logger.exception(f'Callback error: {e}')
        return jsonify({'status': 'error'}), 200


@payment_bp.route('/qris/status/<external_id>', methods=['GET'])
@jwt_required()
def check_qris_status(external_id):
    """Check QRIS payment status"""
    try:
        api_key = _get_xendit_credentials()
        headers = {
            'Authorization': f'Basic {base64.b64encode(api_key.encode()).decode()}'
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

        if not amount or int(amount) < 1000:
            return jsonify({'error': 'Amount must be >= 1000 IDR'}), 400

        if bank not in SUPPORTED_VA_BANKS:
            return jsonify({
                'error': 'Unsupported bank',
                'supported_banks': list(SUPPORTED_VA_BANKS.keys())
            }), 400

        reference_id = f"PF-VA-{datetime.now().strftime('%Y%m%d%H%M%S')}-{amount}"
        user_email = data.get('email', '')
        user_name = data.get('name', 'Customer')

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
            'Authorization': f'Basic {base64.b64encode(api_key.encode()).decode()}',
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

        return jsonify({
            'payment_url': result.get('invoice_url', ''),
            'account_number': result.get('account_number', ''),
            'bank_code': bank_code,
            'bank_name': SUPPORTED_VA_BANKS[bank]['name'],
            'amount': amount,
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
    data = request.json
    current_app.logger.info(f'Xendit VA callback: {json.dumps(data)}')

    try:
        external_id = data.get('external_id', '')
        status = data.get('status', '').upper()
        amount = float(data.get('expected_amount', 0))

        if status == 'PAID':
            current_app.logger.info(f'VA PAID: {external_id}, amount={amount}')
            # TODO: Update user token balance
        elif status == 'EXPIRED':
            current_app.logger.info(f'VA EXPIRED: {external_id}')
        elif status == 'FAILED':
            current_app.logger.error(f'VA FAILED: {external_id}')

        return jsonify({'status': 'received'}), 200
    except Exception as e:
        current_app.logger.exception(f'VA callback error: {e}')
        return jsonify({'status': 'error'}), 200


@payment_bp.route('/va/status/<external_id>', methods=['GET'])
@jwt_required()
def check_va_status(external_id):
    """Check VA payment status"""
    try:
        api_key = _get_xendit_credentials()
        headers = {
            'Authorization': f'Basic {base64.b64encode(api_key.encode()).decode()}'
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
