#!/usr/bin/env python3
"""
ASPI Portal Functional Test Runner - QR MPM
Full automated 4-step flow:
1. /utilities/signature-auth → get auth signature
2. /access-token/b2b → get Bearer token  
3. /utilities/signature-service → get service signature
4. /qr/qr-mpm-generate or /qr/qr-mpm-query → execute test
"""
import requests, json, sys, hashlib, time
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

# ===== CREDENTIALS =====
CLIENT_ID = '19f53f47658f410aa77ecc7aec2d9635'
CLIENT_SECRET = 'm89EqiGKy9JU8IYNGExmcMO/A4JsLJmKHDRQszON1mI='
PRIVATE_KEY = 'Rgf84TC5v0F+L4jZKWdU0wWDuBDfOFZZLXIhp0u7EI4='
BASE = 'https://apidevportal.aspi-indonesia.or.id:44310'

def get_timestamp():
    return datetime.now(timezone(timedelta(hours=7))).strftime('%Y-%m-%dT%H:%M:%S+07:00')

def step1_get_auth_signature(ts):
    """Get signature for access token request"""
    r = requests.post(f'{BASE}/api/v1.0/utilities/signature-auth', headers={
        'accept': 'application/json',
        'X-TIMESTAMP': ts,
        'X-CLIENT-KEY': CLIENT_ID,
        'Private_Key': PRIVATE_KEY
    })
    assert r.status_code == 200, f"sig-auth failed: {r.status_code} {r.text}"
    return r.json()['signature']

def step2_get_access_token(ts, auth_sig):
    """Get B2B access token"""
    r = requests.post(f'{BASE}/api/v1.0/access-token/b2b',
        headers={
            'Content-Type': 'application/json',
            'X-TIMESTAMP': ts,
            'X-CLIENT-KEY': CLIENT_ID,
            'X-SIGNATURE': auth_sig
        },
        json={'grantType': 'client_credentials'}
    )
    assert r.status_code == 200, f"token failed: {r.status_code} {r.text}"
    return r.json()['accessToken']

def step3_get_service_signature(ts, access_token, http_method, endpoint_url, body_str):
    """Get signature for service request via portal utility"""
    # Try with JSON body
    r = requests.post(f'{BASE}/api/v1.0/utilities/signature-service',
        headers={
            'Content-Type': 'application/json',
            'accept': 'application/json',
            'X-TIMESTAMP': ts,
            'X-CLIENT-KEY': CLIENT_ID,
            'Client_Secret': CLIENT_SECRET,
            'HttpMethod': http_method,
            'EndpoinUrl': endpoint_url,
            'AccessToken': access_token,
            'RequestBody': body_str
        }
    )
    if r.status_code == 200:
        return r.json()['signature']
    # Try alternate header casing
    r2 = requests.post(f'{BASE}/api/v1.0/utilities/signature-service',
        headers={
            'Content-Type': 'application/json',
            'accept': 'application/json',
            'X-TIMESTAMP': ts,
            'X-CLIENT-KEY': CLIENT_ID,
            'Client_Secret': CLIENT_SECRET,
            'Httpmethod': http_method,
            'Endpoinurl': endpoint_url,
            'Accesstoken': access_token,
            'Requestbody': body_str
        }
    )
    if r2.status_code == 200:
        return r2.json()['signature']
    # Try with proper JSON body
    r3 = requests.post(f'{BASE}/api/v1.0/utilities/signature-service',
        headers={
            'Content-Type': 'application/json',
            'accept': 'application/json',
            'X-TIMESTAMP': ts,
            'X-CLIENT-KEY': CLIENT_ID,
            'Client_Secret': CLIENT_SECRET,
        },
        json={
            'HttpMethod': http_method,
            'EndpoinUrl': endpoint_url,
            'AccessToken': access_token,
            'RequestBody': body_str
        }
    )
    if r3.status_code == 200:
        return r3.json()['signature']
    print(f"  sig-service failed: {r.status_code} {r.text[:200]}")
    print(f"  sig-service alt: {r2.status_code} {r2.text[:200]}")
    print(f"  sig-service json: {r3.status_code} {r3.text[:200]}")
    return None

def execute_test(test_id, description, endpoint, body_dict, expected_code):
    """Execute a single functional test"""
    print(f"\n{'='*60}")
    print(f"TEST {test_id}: {description}")
    print(f"Expected: {expected_code}")
    print(f"{'='*60}")
    
    ts = get_timestamp()
    body_str = json.dumps(body_dict, separators=(',', ':'))
    
    # Steps 1-2: Get token
    print("  Getting auth signature...")
    auth_sig = step1_get_auth_signature(ts)
    print("  Getting access token...")
    access_token = step2_get_access_token(ts, auth_sig)
    
    # Step 3: Get service signature
    print("  Getting service signature...")
    service_sig = step3_get_service_signature(ts, access_token, 'POST', endpoint, body_str)
    
    if not service_sig:
        print("  FAILED to get service signature!")
        return None
    
    # Step 4: Execute request
    print("  Executing request...")
    ext_id = str(int(time.time() * 1000))
    r = requests.post(f'{BASE}{endpoint}',
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {access_token}',
            'X-TIMESTAMP': ts,
            'X-SIGNATURE': service_sig,
            'ORIGIN': 'https://paperfull.app',
            'X-PARTNER-ID': CLIENT_ID,
            'X-EXTERNAL-ID': ext_id,
            'CHANNEL-ID': '95221',
            'X-IP-ADDRESS': '172.24.281.24',
            'X-DEVICE-ID': '09864ADCASA',
            'X-LATITUDE': '-6.1617169',
            'X-LONGITUDE': '106.664394'
        },
        json=body_dict
    )
    
    resp = r.json()
    actual_code = resp.get('responseCode', 'N/A')
    status = '✅ PASS' if actual_code == expected_code else '❌ FAIL'
    
    print(f"\n  {status}")
    print(f"  Response Code: {actual_code} (expected: {expected_code})")
    print(f"  Response: {json.dumps(resp, indent=2)[:500]}")
    
    return resp

# ===== RUN TESTS =====
if __name__ == "__main__":
    print("ASPI Portal Functional Test - QR MPM")
    print("=" * 60)
    
    # Test 18.6: Generate QR Sukses
    r1 = execute_test("18.6", "Generate QR MPM - Sukses",
        "/api/v1.0/qr/qr-mpm-generate",
        {
            "partnerReferenceNo": "PF-ASPI-20260715001",
            "amount": {"value": "1000.00", "currency": "IDR"},
            "feeAmount": {"value": "0.00", "currency": "IDR"},
            "merchantId": "merch00001",
            "subMerchantId": "310928924949487",
            "storeId": "abcd",
            "terminalId": "213141251124",
            "validityPeriod": "2026-07-15T17:00:00+07:00",
            "additionalInfo": {"deviceId": "12345679237", "channel": "mobilephone"}
        },
        "2004700"
    )
    
    time.sleep(1)
    
    # Test 18.7: Generate QR Gagal - Invalid Merchant
    execute_test("18.7", "Generate QR MPM - Gagal (Invalid Merchant)",
        "/api/v1.0/qr/qr-mpm-generate",
        {
            "partnerReferenceNo": "PF-ASPI-20260715002",
            "amount": {"value": "1000.00", "currency": "IDR"},
            "feeAmount": {"value": "0.00", "currency": "IDR"},
            "merchantId": "invalid_merchant_id_xyz",
            "subMerchantId": "310928924949487",
            "storeId": "abcd",
            "terminalId": "213141251124",
            "validityPeriod": "2026-07-15T17:00:00+07:00",
            "additionalInfo": {"deviceId": "12345679237", "channel": "mobilephone"}
        },
        "4044708"
    )
    
    time.sleep(1)
    
    # Get referenceNo from test 18.6 for query
    ref_no = ""
    if r1 and r1.get('responseCode') == '2004700':
        ref_no = r1.get('referenceNo', 'PF-ASPI-20260715001')
    
    # Test 18.15: Query Payment - Sukses
    execute_test("18.15", "Query Payment - Sukses",
        "/api/v1.0/qr/qr-mpm-query",
        {
            "originalPartnerReferenceNo": "PF-ASPI-20260715001",
            "originalReferenceNo": ref_no or "PF-ASPI-20260715001",
            "serviceCode": "47",
            "merchantId": "merch00001"
        },
        "2005100"
    )
    
    time.sleep(1)
    
    # Test 18.17: Query Payment - Gagal (Not Found)
    execute_test("18.17", "Query Payment - Gagal (Not Found)",
        "/api/v1.0/qr/qr-mpm-query",
        {
            "originalPartnerReferenceNo": "PF-ASPI-INVALID-REF",
            "originalReferenceNo": "PF-ASPI-INVALID-REF",
            "serviceCode": "47",
            "merchantId": "merch00001"
        },
        "4045101"
    )
    
    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETE")
    print("=" * 60)
