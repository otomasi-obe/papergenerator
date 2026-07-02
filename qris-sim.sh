#!/bin/bash
# QRIS Payment Simulator for Paperfull (Xendit Sandbox)
# Usage: ./qris-sim.sh [external_id] [--pay] [--cancel] [--status]
#
# Without args: auto-detect latest pending payment
# --pay:    simulate successful payment via Xendit sandbox
# --cancel: mark as expired
# --status: check current status via Xendit API

set -e

BACKEND="http://127.0.0.1:8001"
API_KEY="xnd_development_NGWjvbxcc5Ty20OCpzBR4VAFvOEbm681YwAtzWMdFWit7SJ9ZnxFd87a42vHQ"
AUTH_HEADER=$(python3 -c "import base64; print('Basic ' + base64.b64encode('${API_KEY}:'.encode()).decode())")

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}━━━ Paperfull QRIS Simulator ━━━${NC}"
echo ""

# Parse args
EXT_ID=""
ACTION="show"

for arg in "$@"; do
  case $arg in
    --pay)    ACTION="pay" ;;
    --cancel) ACTION="cancel" ;;
    --status) ACTION="status" ;;
    *)        EXT_ID="$arg" ;;
  esac
done

# If no external_id, find latest via backend logs
if [ -z "$EXT_ID" ]; then
  echo -e "${YELLOW}Auto-detecting latest payment...${NC}"
  
  # Try to get from PM2 logs (most recent QRIS generation)
  EXT_ID=$(pm2 logs paper-backend-flask --lines 200 --nostream 2>&1 | grep "reference_id\|external_id" | tail -1 | python3 -c "
import sys, re
line = sys.stdin.read().strip()
# Match patterns like reference_id=PF-xxx or external_id: PF-xxx
m = re.search(r'(PF-\d+-\d+)', line)
if m: print(m.group(1))
else: print('')
" 2>/dev/null)
  
  if [ -z "$EXT_ID" ]; then
    echo -e "${RED}No payment found. Generate one first at paperfull.app/tokens/pay${NC}"
    exit 1
  fi
  
  echo -e "${GREEN}Found: ${CYAN}${EXT_ID}${NC}"
fi

# Check status via Xendit API
check_status() {
  local id="$1"
  echo -e "${YELLOW}Checking Xendit status for ${id}...${NC}"
  
  STATUS_RESULT=$(curl -s -X GET "https://api.xendit.co/qr_codes/${id}" \
    -H "Authorization: ${AUTH_HEADER}" \
    -H "Content-Type: application/json" 2>&1)
  
  python3 -c "
import sys, json
try:
    d = json.loads(sys.stdin.read())
    print(f'Status: {d.get(\"status\", \"UNKNOWN\")}')
    print(f'Amount: Rp {d.get(\"amount\", 0)}')
    print(f'QR String: {d.get(\"qr_string\", \"\")}')
    print(f'Expires: {d.get(\"expires_at\", \"\")}')
except:
    print('Failed to parse response')
" <<< "$STATUS_RESULT"
}

case $ACTION in
  show)
    check_status "$EXT_ID"
    echo ""
    echo -e "${YELLOW}Commands:${NC}"
    echo -e "  ${CYAN}./qris-sim.sh ${EXT_ID} --pay${NC}    → Simulate successful payment"
    echo -e "  ${CYAN}./qris-sim.sh ${EXT_ID} --cancel${NC}  → Mark as expired"
    echo -e "  ${CYAN}./qris-sim.sh ${EXT_ID} --status${NC}  → Check status only"
    ;;
  
  status)
    check_status "$EXT_ID"
    ;;
  
  pay)
    echo -e "${GREEN}━━━ Simulating PAYMENT ━━━${NC}"
    echo -e "External ID: ${CYAN}${EXT_ID}${NC}"
    echo ""
    
    # Step 1: Send callback to backend (simulate Xendit webhook)
    echo -e "${YELLOW}[1/2] Sending webhook callback to backend...${NC}"
    
    CALLBACK_RESPONSE=$(curl -s -X POST "${BACKEND}/api/payment/qris/callback" \
      -H "Content-Type: application/json" \
      -d "{
        \"event\": \"qr.payment.succeeded\",
        \"id\": \"sim_pay_$(date +%s)\",
        \"external_id\": \"${EXT_ID}\",
        \"amount\": 1000,
        \"status\": \"PAID\",
        \"payment_method\": \"QRIS\",
        \"paid_at\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
      }" 2>&1)
    
    echo -e "Backend response: ${CYAN}${CALLBACK_RESPONSE}${NC}"
    
    # Step 2: Verify status via Xendit API (sandbox status won't actually change, 
    # but our callback already told backend it's PAID)
    echo -e "${YELLOW}[2/2] Verifying...${NC}"
    
    # Frontend polls check_qris_status endpoint which queries Xendit
    # For sandbox, we need to use Xendit simulator to actually change status
    # OR frontend should also check local callback state
    
    echo ""
    echo -e "${GREEN}✓ Webhook callback sent!${NC}"
    echo -e "${YELLOW}Note: Xendit sandbox QRIS status won't change from API alone.${NC}"
    echo -e "${YELLOW}For frontend auto-update, the payment page polls /api/payment/qris/status${NC}"
    echo ""
    echo -e "${YELLOW}To fully simulate in Xendit dashboard:${NC}"
    echo -e "  1. Open ${CYAN}https://dashboard.xendit.co${NC} → QRIS Simulator"
    echo -e "  2. Paste the QR string from --status output"
    echo -e "  3. Click Pay → Xendit sends real webhook → backend auto-updates"
    ;;
  
  cancel)
    echo -e "${RED}━━━ Simulating EXPIRY ━━━${NC}"
    
    CALLBACK_RESPONSE=$(curl -s -X POST "${BACKEND}/api/payment/qris/callback" \
      -H "Content-Type: application/json" \
      -d "{
        \"event\": \"qr.payment.expired\",
        \"id\": \"sim_exp_$(date +%s)\",
        \"external_id\": \"${EXT_ID}\",
        \"amount\": 1000,
        \"status\": \"EXPIRED\",
        \"payment_method\": \"QRIS\"
      }" 2>&1)
    
    echo -e "Backend response: ${CYAN}${CALLBACK_RESPONSE}${NC}"
    echo -e "${RED}✓ Payment marked as EXPIRED.${NC}"
    ;;
esac
