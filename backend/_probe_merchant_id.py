import os, json
os.environ['DOKU_ENV'] = 'production'
from main import app
from tools.payment.doku import _get_config, _get_b2b_token, _doku_request
from datetime import datetime, timedelta, timezone

with app.app_context():
    cfg = _get_config()
    token = _get_b2b_token()
    
    # Try numeric merchant IDs (common DOKU patterns)
    for mid in ["47435", "2997", "2115", "1", "100", "001"]:
        payload = {
            "partnerReferenceNo": f"PF-DOKU-PROBE-{int(datetime.now().timestamp())}-1000",
            "amount": {"value": "1000.00", "currency": "IDR"},
            "merchantId": mid,
            "terminalId": "PF01",
            "validityPeriod": (datetime.now(timezone(timedelta(hours=7))) + timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M:%S+07:00'),
            "additionalInfo": {"postalCode": "60236", "feeType": "1"}
        }
        result = _doku_request("/snap-adapter/b2b/v1.0/qr/qr-mpm-generate", payload)
        code = result.get("responseCode", "")
        msg = result.get("responseMessage", "")
        print(f"merchantId={mid} → {code} {msg}")
        if code.startswith("200"):
            print(f"\n🎉 FOUND! merchantId = {mid}")
            print(json.dumps(result, indent=2))
            break
        import time; time.sleep(1)  # avoid rate limit
