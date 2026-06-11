#!/bin/bash
# ============================================================
# PAPERFULL.APP — Production Deploy Script
# Runs as: sudo bash deploy.sh
# From: /home/sirobo/papergenerator/
# ============================================================
set -euo pipefail

echo "=========================================="
echo " PaperFull.app — High Concurrency Deploy"
echo "=========================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

# Check root
[[ $EUID -ne 0 ]] && err "Must run as root: sudo bash deploy.sh"

DEPLOY_DIR="/home/sirobo/papergenerator/deploy"
BACKUP_DIR="/home/sirobo/papergenerator/deploy/backups/$(date +%Y%m%d_%H%M%S)"

echo ""
echo "=== STEP 1: Backup current configs ==="
mkdir -p "$BACKUP_DIR"
cp /etc/nginx/nginx.conf "$BACKUP_DIR/nginx.conf.bak" 2>/dev/null || true
cp /etc/nginx/sites-available/paperfull.conf "$BACKUP_DIR/paperfull.conf.bak" 2>/dev/null || true
log "Backups saved to $BACKUP_DIR"

echo ""
echo "=== STEP 2: System tuning (file descriptors & kernel) ==="
cp "$DEPLOY_DIR/99-paperfull.conf" /etc/security/limits.d/99-paperfull.conf
cp "$DEPLOY_DIR/99-paperfull-sysctl.conf" /etc/sysctl.d/99-paperfull.conf
sysctl -p /etc/sysctl.d/99-paperfull.conf
log "System limits & kernel tuning applied"

echo ""
echo "=== STEP 3: Nginx global config ==="
cp "$DEPLOY_DIR/nginx.conf" /etc/nginx/nginx.conf
log "Nginx global config updated (worker_connections=4096, rate limiting)"

echo ""
echo "=== STEP 4: Nginx site config ==="
cp "$DEPLOY_DIR/paperfull.conf" /etc/nginx/sites-available/paperfull.conf
log "Nginx site config updated (keepalive upstream, tiered rate limits)"

echo ""
echo "=== STEP 5: Test Nginx config ==="
nginx -t || err "Nginx config test failed! Check $BACKUP_DIR to rollback."
log "Nginx config test passed"

echo ""
echo "=== STEP 6: Stop current backend ==="
su - sirobo -c "pm2 stop paper-backend-flask" 2>/dev/null || warn "Backend not running (OK)"

echo ""
echo "=== STEP 7: Update PM2 backend to gunicorn ==="
# Delete old process and create new one with gunicorn
su - sirobo -c "pm2 delete paper-backend-flask 2>/dev/null; \
    cd /home/sirobo/papergenerator/backend && \
    pm2 start gunicorn \
        --name paper-backend-flask \
        -- -c gunicorn.conf.py main:app && \
    pm2 save"
log "Backend switched to gunicorn (16 workers × 4 threads)"

echo ""
echo "=== STEP 8: Reload Nginx ==="
systemctl reload nginx
log "Nginx reloaded"

echo ""
echo "=== STEP 9: Health check ==="
sleep 3
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/health 2>/dev/null || echo "000")
if [[ "$HTTP_CODE" == "200" ]]; then
    log "Health check passed (HTTP $HTTP_CODE)"
else
    warn "Health check returned HTTP $HTTP_CODE — check logs"
    echo "  Backend logs: pm2 logs paper-backend-flask --lines 20"
    echo "  Nginx error:  tail -20 /var/log/nginx/error.log"
fi

echo ""
echo "=== STEP 10: Verify worker count ==="
WORKERS=$(pgrep -c -f "gunicorn.*main:app" 2>/dev/null || echo "0")
log "Gunicorn workers running: $WORKERS (expected: 17 = 1 master + 16 workers)"

echo ""
echo "=========================================="
echo " DEPLOY COMPLETE"
echo "=========================================="
echo ""
echo " Capacity estimate:"
echo "   Nginx: 40 workers × 4096 connections = 163,840 max connections"
echo "   Backend: 16 workers × 4 threads = 64 concurrent requests"
echo "   With micro-caching: ~2000-5000 concurrent users"
echo ""
echo " Rollback (if needed):"
echo "   sudo cp $BACKUP_DIR/nginx.conf.bak /etc/nginx/nginx.conf"
echo "   sudo cp $BACKUP_DIR/paperfull.conf.bak /etc/nginx/sites-available/paperfull.conf"
echo "   sudo nginx -t && sudo systemctl reload nginx"
echo "   pm2 delete paper-backend-flask && pm2 start 153"
echo ""
