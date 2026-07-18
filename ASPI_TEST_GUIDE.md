# ASPI Portal Functional Testing Guide
## QR MPM (Service Code: 47 & 51)

**Portal:** https://apidevportal.aspi-indonesia.or.id/
**Login:** anabilhisyam23@gmail.com

---

## 📋 Credentials (ASPI Portal - NOT DOKU)

| Parameter | Value |
|-----------|-------|
| Client ID | `19f53f47658f410aa77ecc7aec2d9635` |
| Client Secret | `m89EqiGKy9JU8IYNGExmcMO/A4JsLJmKHDRQszON1mI=` |
| Private Key (HMAC) | `Rgf84TC5v0F+L4jZKWdU0wWDuBDfOFZZLXIhp0u7EI4=` |
| Public Key | `c376b341aaf5402bad4532d5aa69095e` |

---

## 🔑 Get Bearer Token (Manual - Required)

1. Login to portal
2. Go to: **API → Transfer Kredit → MPM → Aplikasi Pengujian**
3. Open DevTools (F12) → Network tab
4. Click **Try It Out** → **Execute** on any endpoint
5. In Network tab, click the request → Headers → copy `Authorization: Bearer <token>`
6. Use this token in the test script

---

## 🧪 Required Test Scenarios (per ASPI Functional Test V.3.2-4)

### Generate QR MPM (Service Code: 47)
**Endpoint:** `POST /api/v1.0/qr/qr-mpm-generate`

| Test | Scenario | merchantId | Expected responseCode |
|------|----------|------------|----------------------|
| **18.6** | ✅ SUKSES - Show QR Code | `merch00001` | `2004700` |
| **18.7** | ❌ GAGAL - Invalid Merchant | `invalid_merchant` | `4044708` |

### Query Payment (Service Code: 51)
**Endpoint:** `POST /api/v1.0/qr/qr-mpm-query`

| Test | Scenario | originalPartnerReferenceNo | Expected responseCode |
|------|----------|---------------------------|----------------------|
| **18.15** | ✅ SUKSES - Successful Transaction | From 18.6 response | `2005100` |
| **18.17** | ❌ GAGAL - Not Found | `PF-ASPI-INVALID-REF` | `4045101` |

---

## 📦 Request Bodies

### 18.6 Generate QR - SUKSES
```json
{
  "partnerReferenceNo": "PF-ASPI-20260715001",
  "amount": { "value": "1000.00", "currency": "IDR" },
  "feeAmount": { "value": "0.00", "currency": "IDR" },
  "merchantId": "merch00001",
  "subMerchantId": "submerch00001",
  "storeId": "store00001",
  "terminalId": "term00001",
  "validityPeriod": "2026-07-15T15:30:00+07:00",
  "additionalInfo": { "deviceId": "12345679237", "channel": "mobilephone" }
}
```

### 18.7 Generate QR - GAGAL
```json
{
  "partnerReferenceNo": "PF-ASPI-20260715002",
  "amount": { "value": "1000.00", "currency": "IDR" },
  "feeAmount": { "value": "0.00", "currency": "IDR" },
  "merchantId": "invalid_merchant_id_xyz",
  "subMerchantId": "submerch00001",
  "storeId": "store00001",
  "terminalId": "term00001",
  "validityPeriod": "2026-07-15T15:30:00+07:00",
  "additionalInfo": { "deviceId": "12345679237", "channel": "mobilephone" }
}
```

### 18.15 Query Payment - SUKSES
```json
{
  "originalPartnerReferenceNo": "PF-ASPI-20260715001",
  "originalReferenceNo": "PF-ASPI-20260715001",
  "serviceCode": "47",
  "merchantId": "merch00001"
}
```

### 18.17 Query Payment - GAGAL
```json
{
  "originalPartnerReferenceNo": "PF-ASPI-INVALID-REF",
  "originalReferenceNo": "PF-ASPI-INVALID-REF",
  "serviceCode": "47",
  "merchantId": "merch00001"
}
```

---

## 🔐 Headers (Required for ALL requests)

| Header | Value |
|--------|-------|
| `Content-Type` | `application/json` |
| `Authorization` | `Bearer <YOUR_TOKEN_FROM_PORTAL>` |
| `X-TIMESTAMP` | `2026-07-15T08:30:00.123Z` (ISO 8601 UTC, current time) |
| `X-SIGNATURE` | `HMAC-SHA512(CLIENT_SECRET, stringToSign)` |
| `X-PARTNER-ID` | `19f53f47658f410aa77ecc7aec2d9635` |
| `X-EXTERNAL-ID` | Unique per request (e.g. `ext-1784108167141`) |
| `CHANNEL-ID` | `95221` (confirm with DOKU) |
| `ORIGIN` | `https://paperfull.app` |
| `X-IP-ADDRESS` | `172.24.281.24` |
| `X-DEVICE-ID` | `09864ADCASA` |
| `X-LATITUDE` | `-6.1617169` |
| `X-LONGITUDE` | `106.664394` |

---

## 📝 stringToSign Format

```
HTTP_METHOD:ENDPOINT_PATH:ACCESS_TOKEN:TIMESTAMP:MINIFIED_REQUEST_BODY
```

Example:
```
POST:/api/v1.0/qr/qr-mpm-generate:eyJhbGciOi...:2026-07-15T08:30:00.123Z:{"partnerReferenceNo":"PF-ASPI-20260715001","amount":{"value":"1000.00","currency":"IDR"},...}
```

**HMAC Key:** Base64 decode of Client Secret: `m89EqiGKy9JU8IYNGExmcMO/A4JsLJmKHDRQszON1mI=`

---

## 🚀 Quick Test with curl (Paste into Terminal)

```bash
# 1. Set your token from portal
export ASPI_TOKEN="your_bearer_token_here"

# 2. Test 18.6 - Generate QR Sukses
curl -X POST "https://apidevportal.aspi-indonesia.or.id/api/v1.0/qr/qr-mpm-generate" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ASPI_TOKEN" \
  -H "X-TIMESTAMP: 2026-07-15T08:30:00.123Z" \
  -H "X-PARTNER-ID: 19f53f47658f410aa77ecc7aec2d9635" \
  -H "X-EXTERNAL-ID: ext-$(date +%s%3N)" \
  -H "CHANNEL-ID: 95221" \
  -H "ORIGIN: https://paperfull.app" \
  -H "X-SIGNATURE: GENERATE_VIA_SCRIPT" \
  -d '{
    "partnerReferenceNo": "PF-ASPI-20260715001",
    "amount": {"value": "1000.00", "currency": "IDR"},
    "feeAmount": {"value": "0.00", "currency": "IDR"},
    "merchantId": "merch00001",
    "subMerchantId": "submerch00001",
    "storeId": "store00001",
    "terminalId": "term00001",
    "validityPeriod": "2026-07-15T15:30:00+07:00",
    "additionalInfo": {"deviceId": "12345679237", "channel": "mobilephone"}
  }'
```

---

## 📄 After Testing

1. Portal ASPI → **Aktivitas Aplikasi Pengujian** → View/Download PDF
2. PDF must show: **4 test cases** (2 Generate + 2 Query) with PASS
3. Send PDF to **DOKU** → DOKU registers to ASPI officially

---

## ✅ Next Steps for You

1. **Get token** from portal (DevTools Network tab)
2. **Run the Python script** at `/home/sirobo/papergenerator/test_aspi_portal.py`
3. **Or use portal "Try It Out"** directly with bodies above
4. **Download PDF** → send to DOKU

---

## 🔧 Files Created

- `/home/sirobo/papergenerator/test_aspi_portal.py` - Automated test script
- `/home/sirobo/papergenerator/ASPI_TEST_GUIDE.md` - This guide