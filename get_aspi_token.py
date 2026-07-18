#!/usr/bin/env python3
"""
ASPI OAuth Token + Signature Generator
Run: python3 get_aspi_token.py
"""
import base64
import hmac
import hashlib
import json
import time
import requests
from datetime import datetime, timezone, timedelta

# ASPI Portal Credentials (dari screenshot)
CLIENT_ID = "19f53f47658f410aa77ecc7aec2d9635"
CLIENT_SECRET = "m89EqiGKy9JU8IYNGExmcMO/A4JsLJmKHDRQszON1mI="
PRIVATE_KEY_B64 = "Rgf84TC5v0F+L4jZKWdU0wWDuBDfOFZZLXIhp0u7EI4="  # base64 encoded

# ASPI Endpoints
OAUTH_URL = "https://apidevportal.aspi-indonesia.or.id/api/oauth/token"
BASE_URL = "https://apidevportal.aspi-indonesia.or.id/snap-adapter/b2b/v1.0/qr"

def get_oauth_token():
    """Get ASPI OAuth token via Client Credentials"""
    creds = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {creds}"
    }
    data = "grant_type=client_credentials&scope=qr-mpm"
    resp = requests.post(OAUTH_URL, headers=headers, data=data)
    resp.raise_for_status()
    token_data = resp.json()
    return token_data["access_token"]

def generate_signature(http_method, endpoint_path, access_token, timestamp, request_body=""):
    """
    ASPI Signature: HMAC-SHA512(ClientSecret, stringToSign)
 stringToSign = HTTP_METHOD:ENDPOINT_PATH:ACCESS_TOKEN:TIMESTAMP:MINIFIED_REQUEST_BODY
    """
    # Minify JSON body (remove whitespace)
    if request_body:
        body_minified = json.dumps(json.loads(request_body), separators=(',', ':'))
    else:
        body_minified = ""
    
    string_to_sign = f"{http_method}:{endpoint_path}:{access_token}:{timestamp}:{body_minified}"
    print(f"String to sign:\n{string_to_sign}\n")
    
    # HMAC-SHA512 with Client Secret (base64 decoded)
    secret_bytes = base64.b64decode(CLIENT_SECRET)
    signature = hmac.new(secret_bytes, string_to_sign.encode(), hashlib.sha512).digest()
    return base64.b64encode(signature).decode()

def build_headers(access_token, signature, timestamp, partner_id=CLIENT_ID):
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "X-TIMESTAMP": timestamp,
        "X-SIGNATURE": signature,
        "X-PARTNER-ID": partner_id,
        "Accept": "application/json"
    }

def test_generate_qr(access_token):
    """Test Generate QR MPM (Service Code 47)"""
    endpoint = "/qr-mpm-generate"
    url = f"{BASE_URL}{endpoint}"
    
    # Valid request (SUKSES)
    body = {
        "partnerReferenceNo": f"PF-ASPI-TEST-{int(time.time())}",
        "amount": {"value": "1000.00", "currency": "IDR"},
        "merchantId": "47435",
        "terminalId": "98686",
        "validityPeriod": (datetime.now(timezone(timedelta(hours=7))) + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%S+07:00"),
        "additionalInfo": {"postalCode": "12345", "feeType": "1"}
    }
    
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    body_json = json.dumps(body, separators=(',', ':'))
    signature = generate_signature("POST", endpoint, access_token, timestamp, body_json)
    headers = build_headers(access_token, signature, timestamp)
    
    print("=" * 60)
    print("TEST 1: Generate QR MPM - SUKSES")
    print("=" * 60)
    print(f"URL: {url}")
    print(f"Headers: {json.dumps(headers, indent=2)}")
    print(f"Body: {json.dumps(body, indent=2)}")
    print()
    
    resp = requests.post(url, headers=headers, json=body)
    print(f"Status: {resp.status_code}")
    print(f"Response: {json.dumps(resp.json(), indent=2)}")
    
    result = resp.json()
    ref_no = result.get("referenceNo") or body["partnerReferenceNo"]
    return ref_no

def test_generate_qr_failed(access_token):
    """Test Generate QR MPM - GAGAL (amount 0)"""
    endpoint = "/qr-mpm-generate"
    url = f"{BASE_URL}{endpoint}"
    
    body = {
        "partnerReferenceNo": f"PF-ASPI-FAIL-{int(time.time())}",
        "amount": {"value": "0.00", "currency": "IDR"},  # INVALID amount
        "merchantId": "47435",
        "terminalId": "98686",
        "validityPeriod": (datetime.now(timezone(timedelta(hours=7))) + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%S+07:00"),
        "additionalInfo": {"postalCode": "12345", "feeType": "1"}
    }
    
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    body_json = json.dumps(body, separators=(',', ':'))
    signature = generate_signature("POST", endpoint, access_token, timestamp, body_json)
    headers = build_headers(access_token, signature, timestamp)
    
    print("\n" + "=" * 60)
    print("TEST 2: Generate QR MPM - GAGAL (amount 0)")
    print("=" * 60)
    print(f"Body: {json.dumps(body, indent=2)}")
    print()
    
    resp = requests.post(url, headers=headers, json=body)
    print(f"Status: {resp.status_code}")
    print(f"Response: {json.dumps(resp.json(), indent=2)}")

def test_query_payment(access_token, ref_no):
    """Test Query Payment (Service Code 51)"""
    endpoint = "/qr-mpm-query"
    url = f"{BASE_URL}{endpoint}"
    
    body = {
        "originalPartnerReferenceNo": ref_no,
        "originalReferenceNo": ref_no,
        "serviceCode": "47",
        "merchantId": "47435"
    }
    
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    body_json = json.dumps(body, separators=(',', ':'))
    signature = generate_signature("POST", endpoint, access_token, timestamp, body_json)
    headers = build_headers(access_token, signature, timestamp)
    
    print("\n" + "=" * 60)
    print("TEST 3: Query Payment - SUKSES")
    print("=" * 60)
    print(f"URL: {url}")
    print(f"Body: {json.dumps(body, indent=2)}")
    print()
    
    resp = requests.post(url, headers=headers, json=body)
    print(f"Status: {resp.status_code}")
    print(f"Response: {json.dumps(resp.json(), indent=2)}")

def test_query_payment_failed(access_token):
    """Test Query Payment - GAGAL (ref tidak ada)"""
    endpoint = "/qr-mpm-query"
    url = f"{BASE_URL}{endpoint}"
    
    body = {
        "originalPartnerReferenceNo": "PF-ASPI-INVALID-REF",
        "originalReferenceNo": "PF-ASPI-INVALID-REF",
        "serviceCode": "47",
        "merchantId": "47435"
    }
    
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    body_json = json.dumps(body, separators=(',', ':'))
    signature = generate_signature("POST", endpoint, access_token, timestamp, body_json)
    headers = build_headers(access_token, signature, timestamp)
    
    print("\n" + "=" * 60)
    print("TEST 4: Query Payment - GAGAL (ref tidak valid)")
    print("=" * 60)
    print(f"Body: {json.dumps(body, indent=2)}")
    print()
    
    resp = requests.post(url, headers=headers, json=body)
    print(f"Status: {resp.status_code}")
    print(f"Response: {json.dumps(resp.json(), indent=2)}")

if __name__ == "__main__":
    print("🔐 Getting ASPI OAuth token...")
    token = get_oauth_token()
    print(f"✅ Token acquired: {token[:40]}...\n")
    
    # Test Generate QR MPM - Sukses
    ref = test_generate_qr(token)
    
    # Test Generate QR MPM - Gagal
    test_generate_qr_failed(token)
    
    # Test Query Payment - Sukses (pakai ref dari test 1)
    test_query_payment(token, ref)
    
    # Test Query Payment - Gagal
    test_query_payment_failed(token)
    
    print("\n✅ All tests completed. Check responses for responseCode 2004700 (sukses) vs 400xxxx (gagal)")
    print("📄 Download PDF dari portal ASPI > Aktivitas Aplikasi Pengujian > kirim ke DOKU")