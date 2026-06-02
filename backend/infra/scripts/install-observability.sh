#!/bin/bash
# infra/scripts/install-observability.sh — bring up the local observability
# stack (Prometheus + Grafana + Loki + Promtail + GlitchTip) via Docker.
#
# Prerequisite: docker + docker compose plugin installed on the host.
#   sudo apt-get install -y docker.io docker-compose-plugin
#   sudo usermod -aG docker "$USER"  # then re-login
#
# Usage:
#   bash infra/scripts/install-observability.sh up
#   bash infra/scripts/install-observability.sh down
#   bash infra/scripts/install-observability.sh logs prometheus
#
# Endpoints (after up):
#   Grafana    http://localhost:3000  (admin / $GRAFANA_ADMIN_PASSWORD)
#   Prometheus http://localhost:9090
#   GlitchTip  http://localhost:8092
#   Loki       http://localhost:3100/ready
set -euo pipefail

cd "$(dirname "$0")/../observability"

# Detect compose binary: docker compose (v2) preferred, docker-compose (v1) fallback.
if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE="docker-compose"
else
  echo "Neither 'docker compose' nor 'docker-compose' found." >&2
  exit 1
fi

CMD="${1:-up}"
case "$CMD" in
  up)
    $COMPOSE up -d
    echo "Observability stack is starting…"
    echo "Grafana:    http://localhost:3000"
    echo "Prometheus: http://localhost:9090"
    echo "GlitchTip:  http://localhost:8092"
    ;;
  down)
    $COMPOSE down
    ;;
  logs)
    $COMPOSE logs -f --tail=100 "${2:-}"
    ;;
  status)
    $COMPOSE ps
    ;;
  *)
    echo "Usage: $0 {up|down|logs [service]|status}" >&2
    exit 1
    ;;
esac
