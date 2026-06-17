#!/bin/bash
#
# Paper Generator Manager
# 1=start(skip) 2=build+start 3=stop 4=status
#

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; GRAY='\033[0;37m'; NC='\033[0m'

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$APP_DIR/backend"
FRONTEND_DIR="$APP_DIR/frontend"
BACKEND_LOG_DIR="$BACKEND_DIR/log"
FRONTEND_LOG_DIR="$FRONTEND_DIR/log"

FRONTEND_PORT=8000
BACKEND_PORT=8001

print_header() {
    echo ""; echo -e "${CYAN}╔════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║      Paper Generator Manager           ║${NC}"
    echo -e "${CYAN}║    Backend:8001 • Frontend:8000        ║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════╝${NC}"; echo ""
}

port_listening() { ss -tlnp 2>/dev/null | grep -q ":$1 "; }

is_running() { port_listening $BACKEND_PORT; }

stop_all() {
    echo -e "${YELLOW}Menghentikan semua service...${NC}"; echo ""
    command -v pm2 &>/dev/null || { echo -e "   ${RED}ERROR${NC} - pm2 tidak ditemukan"; return 1; }
    pm2 delete paper-frontend 2>/dev/null && echo -e "   ${GREEN}✓${NC} Frontend dihentikan" || echo -e "   ${GRAY}○${NC} Frontend tidak berjalan"
    pm2 delete paper-backend-flask 2>/dev/null && echo -e "   ${GREEN}✓${NC} Backend dihentikan" || echo -e "   ${GRAY}○${NC} Backend tidak berjalan"
    pm2 delete paper-backend 2>/dev/null
    pm2 delete paper-worker 2>/dev/null && echo -e "   ${GREEN}✓${NC} Worker dihentikan" || echo -e "   ${GRAY}○${NC} Worker tidak berjalan"
    echo ""; echo -e "${GREEN}Semua service dihentikan!${NC}"; echo ""
}

check_python_syntax() {
    echo -e "${YELLOW}Memeriksa sintaks Python...${NC}"
    local errors=0
    local venv_present=false
    [ -d "$BACKEND_DIR/.venv" ] && venv_present=true
    while IFS= read -r -d '' f; do
        # Skip .venv files
        if $venv_present && [[ "$f" == "$BACKEND_DIR/.venv"* ]]; then continue; fi
        python3 -m py_compile "$f" 2>/dev/null || {
            echo -e "   ${RED}✗${NC} Syntax error: $f"
            python3 -m py_compile "$f" 2>&1 | head -3
            ((errors++))
        }
    done < <(find "$BACKEND_DIR" -name '*.py' -print0)
    if [ $errors -eq 0 ]; then
        echo -e "   ${GREEN}✓${NC} Tidak ada error sintaks Python"
    else
        echo -e "   ${RED}✗${NC} Ditemukan $errors error sintaks Python"
        return 1
    fi
}

build_frontend() {
    echo -e "${YELLOW}Building Frontend...${NC}"
    cd "$FRONTEND_DIR"; [ ! -d node_modules ] && npm install
    chmod -R +x node_modules/.bin/ 2>/dev/null || true
    npx vite build
    if [ $? -eq 0 ]; then echo -e "   ${GREEN}✓${NC} Frontend build berhasil"; else echo -e "   ${RED}✗${NC} Frontend build gagal"; exit 1; fi
}

do_start_services() {
    mkdir -p "$BACKEND_LOG_DIR" "$FRONTEND_LOG_DIR"

    echo -e "${YELLOW}Starting Frontend...${NC}"
    cd "$FRONTEND_DIR"
    pm2 start proxy-server.cjs --name "paper-frontend" \
        --log "$FRONTEND_LOG_DIR/frontend-out.log" \
        --error "$FRONTEND_LOG_DIR/frontend-error.log" 2>/dev/null
    if port_listening $FRONTEND_PORT; then
        echo -e "   ${GREEN}✓${NC} Frontend started on port $FRONTEND_PORT"
    else
        echo -e "   ${YELLOW}⚠${NC} Port $FRONTEND_PORT sudah dipakai nginx (normal)"
    fi
    echo ""

    echo -e "${YELLOW}Starting Backend...${NC}"
    cd "$BACKEND_DIR"
    killall -9 gunicorn 2>/dev/null || true
    pm2 start ../ecosystem.config.cjs --only paper-backend-flask 2>&1
    echo -e "   ${GREEN}✓${NC} Backend started on port $BACKEND_PORT"
    echo ""

    echo -e "${YELLOW}Starting RQ Worker...${NC}"
    cd "$BACKEND_DIR"
    pm2 start ../ecosystem.config.cjs --only paper-worker 2>&1
    echo -e "   ${GREEN}✓${NC} RQ Worker started"
    echo ""

    pm2 save
    echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Services Started!${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
    echo -e "   Frontend:  ${CYAN}http://localhost:$FRONTEND_PORT${NC}"
    echo -e "   Backend:   ${CYAN}http://localhost:$BACKEND_PORT${NC}"; echo ""
}

do_start() {
    echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  Memulai Paper Generator${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"; echo ""

    if is_running; then
        echo -e "   ${GREEN}✓${NC} Paper Generator sudah aktif — dilewati"; echo ""
        return 0
    fi

    stop_all
    echo -e "${GRAY}(Lewati build — pakai dist/ yang ada)${NC}"; echo ""
    do_start_services
}

build_and_start() {
    echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  Memulai Paper Generator (Build + Start)${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"; echo ""

    stop_all; check_python_syntax; echo ""
    build_frontend; echo ""
    do_start_services
}

check_status() {
    echo -e "${YELLOW}Status Server:${NC}"; echo ""
    echo -e "${YELLOW}PM2 Processes:${NC}"
    pm2 list 2>/dev/null | grep paper || echo -e "   ${GRAY}○${NC} Tidak ada proses paper"
    echo ""; echo -e "${YELLOW}Port Status:${NC}"
    port_listening $FRONTEND_PORT && echo -e "   ${GREEN}✓${NC} Port $FRONTEND_PORT (Frontend): LISTENING" || echo -e "   ${RED}✗${NC} Port $FRONTEND_PORT (Frontend): NOT LISTENING"
    port_listening $BACKEND_PORT && echo -e "   ${GREEN}✓${NC} Port $BACKEND_PORT (Backend): LISTENING" || echo -e "   ${RED}✗${NC} Port $BACKEND_PORT (Backend): NOT LISTENING"
    echo ""
}

show_menu() {
    echo -e "${CYAN}Pilih opsi:${NC}"; echo ""
    echo "  1) Start (skip kalau sudah jalan)"
    echo "  2) Build + Start (cek Python + build frontend)"
    echo "  3) Stop semua service"
    echo "  4) Cek status"
    echo "  5) Cek sintaks Python saja"
    echo ""; read -rp "Masukkan pilihan [1-5]: " choice
    case $choice in
        1) do_start ;; 2) build_and_start ;; 3) stop_all ;; 4) check_status ;; 5) check_python_syntax ;;
        *) echo -e "${RED}Pilihan tidak valid${NC}" ;;
    esac
}

print_header
case "$1" in
    1|start)  do_start ;;
    2|build)  build_and_start ;;
    3|stop)   stop_all ;;
    4|status) check_status ;;
    5|syntax) check_python_syntax ;;
    *)        show_menu ;;
esac
