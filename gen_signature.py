#!/usr/bin/env python3
"""
ASPI X-SIGNATURE Generator
Usage: python3 gen_signature.py
Generates X-SIGNATURE for ASPI Portal testing
"""
import base64
import hmac
import hashlib
import json

# ===== ASPI CREDENTIALS =====
CLIENT_SECRET_B64 = "m89EqiGKy9JU8IYNGExmcMO/A4JsLJmKHDRQszON1mI="
SIGNING_KEY = base64.b64decode(CLIENT_SECRET_B64)

def generate_signature(method, endpoint, access_token, timestamp, body):
    """
    ASPI X-SIGNATURE = HMAC-SHA512(SIGNING_KEY, stringToSign)
    stringToSign = HTTP_METHOD:ENDPOINT_PATH:ACCESS_TOKEN:TIMESTAMP:MINIFIED_BODY
    """
    body_min = json.dumps(body, separators=(',', ':')) if body else ""
    string_to_sign = f"{method}:{endpoint}:{access_token}:{timestamp}:{body_min}"
    
    signature = hmac.new(SIGNING_KEY, string_to_sign.encode(), hashlib.sha512).digest()
    signature_b64 = base64.b64encode(signature).decode()
    
    return signature_b64, string_to_sign

# ===== EXAMPLE TEST DATA =====
# GANTI INI DENGAN DATA ASLI
ACCESS_TOKEN = "PASTE_BEARER_TOKEN_FROM_PORTAL_HERE"  # <-- ISI INI
TIMESTAMP = "2026-07-15T08:30:00.123Z"  # <-- WAKTU SEKARANG (ISO8601 UTC)

# Test 18.6 Generate QR Sukses
BODY_18_6 = {
    "partnerReferenceNo": "PF-ASPI-20260715001",
    "amount": {"value": "1000.00", "currency": "IDR"},
    "feeAmount": {"value": "0.00", "currency": "IDR"},
    "merchantId": "merch00001",
    "subMerchantId": "submerch00001",
    "storeId": "store00001",
    "terminalId": "term00001",
    "validityPeriod": "2026-07-15T15:30:00+07:00",
    "additionalInfo": {"deviceId": "12345679237", "channel": "mobilephone"}
}

# Test 18.7 Generate QR Gagal
BODY_18_7 = {
    "partnerReferenceNo": "PF-ASPI-20260715002",
    "amount": {"value": "1000.00", "currency": "IDR"},
    "feeAmount": {"value": "0.00", "currency": "IDR"},
    "merchantId": "invalid_merchant_id_xyz",
    "subMerchantId": "submerch00001",
    "storeId": "store00001",
    "terminalId": "term00001",
    "validityPeriod": "2026-07-15T15:30:00+07:00",
    "additionalInfo": {"deviceId": "12345679237", "channel": "mobilephone"}
}

# Test 18.15 Query Sukses
BODY_18_15 = {
    "originalPartnerReferenceNo": "PF-ASPI-20260715001",
    "originalReferenceNo": "PF-ASPI-20260715001",
    "serviceCode": "47",
    "merchantId": "merch00001"
}

# Test 18.17 Query Gagal
BODY_18_17 = {
    "originalPartnerReferenceNo": "PF-ASPI-INVALID-REF",
    "originalReferenceNo": "PF-ASPI-INVALID-REF",
    "serviceCode": "47",
    "merchantId": "merch00001"
}

if __name__ == "__main__":
    if ACCESS_TOKEN == "PASTE_BEARER_TOKEN_FROM_PORTAL_HERE":
        print("❌ EDIT SCRIPT DULU: isi ACCESS_TOKEN di baris 37")
        exit(1)
    
    print("="*60)
    print("ASPI X-SIGNATURE GENERATOR")
    print("="*60)
    print(f"Access Token: {ACCESS_TOKEN[:40]}...")
    print(f"Timestamp: {TIMESTAMP}")
    print(f"Signing Key: {CLIENT_SECRET_B64[:20]}... (base64 decoded)")
    print()
    
    tests = [
        ("18.6 Generate QR Sukses", "POST", "/api/v1.0/qr/qr-mpm-generate", BODY_18_6),
        ("18.7 Generate QR Gagal", "POST", "/api/v1.0/qr/qr-mpm-generate", BODY_18_7),
        ("18.15 Query Sukses", "POST", "/api/v1.0/qr/qr-mpm-query", BODY_18_15),
        ("18.17 Query Gagal", "POST", "/api/v1.0/qr/qr-mpm-query", BODY_18_17),
    ]
    
    for name, method, endpoint, body in tests:
        sig, sts = generate_signature(method, endpoint, ACCESS_TOKEN, TIMESTAMP, body)
        print(f"--- {name} ---")
        print(f"Endpoint: {method} {endpoint}")
        print(f"X-SIGNATURE: {sig}")
        print(f"stringToSign: {sts}")
        print()
    
    print("="*60)
    print("COPY X-SIGNATURE KE PORTAL / CURL")
    print("Header X-TIMESTAMP harus sama persis dengan di atas!")
    print("="*60)