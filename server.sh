#!/bin/bash
#
# Paper Generator Manager
# Mengelola Paper Generator dengan Backend Python (8001)
#

# ─── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
GRAY='\033[0;37m'
NC='\033[0m'

# ─── Paths & Ports ────────────────────────────────────────────────────────────
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$APP_DIR/backend"
FRONTEND_DIR="$APP_DIR/frontend"
BACKEND_LOG_DIR="$BACKEND_DIR/log"
FRONTEND_LOG_DIR="$FRONTEND_DIR/log"

FRONTEND_PORT=8000
BACKEND_PORT=8001

# ─── Header ───────────────────────────────────────────────────────────────────
print_header() {
    echo ""
    echo -e "${CYAN}╔════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║      Paper Generator Manager           ║${NC}"
    echo -e "${CYAN}║    Backend:8001 • Frontend:8000        ║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════╝${NC}"
    echo ""
}

# ─── Helpers ──────────────────────────────────────────────────────────────────
port_listening() {
    if command -v ss &>/dev/null; then
        ss -tlnp 2>/dev/null | grep -q ":$1 "
    elif command -v netstat &>/dev/null; then
        netstat -tlnp 2>/dev/null | grep -q ":$1 "
    else
        lsof -i tcp:"$1" &>/dev/null
    fi
}

pm2_running() { pm2 list 2>/dev/null | grep -q "$1"; }

# ─── Stop All ─────────────────────────────────────────────────────────────────
stop_all() {
    echo -e "${YELLOW}Menghentikan semua service...${NC}"
    echo ""

    if ! command -v pm2 &>/dev/null; then
        echo -e "   ${RED}ERROR${NC} - pm2 tidak ditemukan"
        return 1
    fi

    pm2 delete paper-frontend 2>/dev/null && echo -e "   ${GREEN}✓${NC} Frontend dihentikan" || echo -e "   ${GRAY}○${NC} Frontend tidak berjalan"
    pm2 delete paper-backend-flask 2>/dev/null && echo -e "   ${GREEN}✓${NC} Backend dihentikan" || echo -e "   ${GRAY}○${NC} Backend tidak berjalan"
    pm2 delete paper-backend 2>/dev/null
    pm2 delete paper-worker 2>/dev/null && echo -e "   ${GREEN}✓${NC} Worker dihentikan" || echo -e "   ${GRAY}○${NC} Worker tidak berjalan"

    echo ""
    echo -e "${GREEN}Semua service dihentikan!${NC}"
    echo ""
}

# ─── Build Frontend ───────────────────────────────────────────────────────────
build_frontend() {
    echo -e "${YELLOW}Building Frontend...${NC}"
    cd "$FRONTEND_DIR"
    [ ! -d node_modules ] && npm install
    chmod -R +x node_modules/.bin/ 2>/dev/null || true
    npx vite build
    if [ $? -eq 0 ]; then
        echo -e "   ${GREEN}✓${NC} Frontend build berhasil"
    else
        echo -e "   ${RED}✗${NC} Frontend build gagal"
        exit 1
    fi
}

# ─── Start with Python Backend ────────────────────────────────────────────────
start_server() {
    echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  Memulai Frontend dan Backend${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
    echo ""

    stop_all

    mkdir -p "$BACKEND_LOG_DIR"
    mkdir -p "$FRONTEND_LOG_DIR"

    build_frontend
    echo ""

    echo -e "${YELLOW}Starting Frontend...${NC}"
    cd "$FRONTEND_DIR"
    # Nginx sudah serve dist/ di port 8000, PM2 frontend sebagai fallback saja
    pm2 start proxy-server.cjs --name "paper-frontend" \
        --log "$FRONTEND_LOG_DIR/frontend-out.log" \
        --error "$FRONTEND_LOG_DIR/frontend-error.log" 2>/dev/null
    if port_listening $FRONTEND_PORT; then
        echo -e "   ${GREEN}✓${NC} Frontend started on port $FRONTEND_PORT (nginx primary, PM2 fallback)"
    else
        echo -e "   ${YELLOW}⚠${NC} Port $FRONTEN_PORT sudah dipakai nginx (normal — nginx serve langsung)"
    fi
    echo ""

    echo -e "${YELLOW}Starting Backend...${NC}"
    cd "$BACKEND_DIR"
    pm2 start gunicorn --name "paper-backend-flask" --interpreter python3 \
        --log "$BACKEND_LOG_DIR/backend-out.log" \
        --error "$BACKEND_LOG_DIR/backend-error.log" \
        -- -c gunicorn.conf.py main:app
    echo -e "   ${GREEN}✓${NC} Backend started on port $BACKEND_PORT (gunicorn 16w×4t)"
    echo ""

    echo -e "${YELLOW}Starting RQ Worker...${NC}"
    cd "$BACKEND_DIR"
    pm2 start worker.py --name paper-worker --interpreter python3 \
        --log "$BACKEND_LOG_DIR/worker-out.log" \
        --error "$BACKEND_LOG_DIR/worker-error.log" 2>/dev/null
    echo -e "   ${GREEN}✓${NC} RQ Worker started (queue: paper)"
    echo ""

    pm2 save

    echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Services Started!${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
    echo -e "   Frontend:  ${CYAN}http://localhost:$FRONTEND_PORT${NC}"
    echo -e "   Backend:   ${CYAN}http://localhost:$BACKEND_PORT${NC}"
    echo ""
}

# ─── Status ───────────────────────────────────────────────────────────────────
check_status() {
    echo -e "${YELLOW}Status Server:${NC}"
    echo ""

    echo -e "${YELLOW}PM2 Processes:${NC}"
    if command -v pm2 &>/dev/null; then
        pm2 list | grep paper
    else
        echo -e "   ${RED}✗${NC} pm2 tidak terinstall"
    fi

    echo ""
    echo -e "${YELLOW}Port Status:${NC}"
    
    if port_listening $FRONTEND_PORT; then
        echo -e "   ${GREEN}✓${NC} Port $FRONTEND_PORT (Frontend): LISTENING"
    else
        echo -e "   ${RED}✗${NC} Port $FRONTEND_PORT (Frontend): NOT LISTENING"
    fi
    
    if port_listening $BACKEND_PORT; then
        echo -e "   ${GREEN}✓${NC} Port $BACKEND_PORT (Backend): LISTENING"
    else
        echo -e "   ${RED}✗${NC} Port $BACKEND_PORT (Backend): NOT LISTENING"
    fi

    echo ""
    echo -e "${YELLOW}Dependencies:${NC}"
    command -v node    &>/dev/null && echo -e "   ${GREEN}✓${NC} Node.js: $(node -v)" || echo -e "   ${RED}✗${NC} Node.js: Not installed"
    command -v npm     &>/dev/null && echo -e "   ${GREEN}✓${NC} npm:     $(npm -v)" || echo -e "   ${RED}✗${NC} npm:     Not installed"
    command -v pm2     &>/dev/null && echo -e "   ${GREEN}✓${NC} pm2:     $(pm2 -v)" || echo -e "   ${RED}✗${NC} pm2:     Not installed"
    command -v python3 &>/dev/null && echo -e "   ${GREEN}✓${NC} Python:  $(python3 --version)" || echo -e "   ${RED}✗${NC} Python:  Not installed"

    echo ""
}

# ─── Interactive Menu ─────────────────────────────────────────────────────────
show_menu() {
    echo -e "${CYAN}Pilih opsi:${NC}"
    echo ""
    echo "  1) Start Frontend dan Backend"
    echo "  2) Stop semua service"
    echo "  3) Cek status"
    echo ""
    read -rp "Masukkan pilihan [1-3]: " choice
    
    case $choice in
        1)
            start_server
            ;;
        2)
            stop_all
            ;;
        3)
            check_status
            ;;
        *)
            echo -e "${RED}Pilihan tidak valid${NC}"
            ;;
    esac
}

# ─── Main ─────────────────────────────────────────────────────────────────────
print_header

case "$1" in
    1|start)
        start_server
        ;;
    2|stop)
        stop_all
        ;;
    3|status)
        check_status
        ;;
    *)
        show_menu
        ;;
esac
