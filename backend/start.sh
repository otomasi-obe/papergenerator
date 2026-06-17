#!/bin/bash
# Production startup: Gunicorn gthread workers (sync + threads)
# 16 workers × 8 threads = 128 concurrent request slots.
# For 1000+ users: nginx handles static assets + connection queuing.
# PostgreSQL pool: 3 base + 4 overflow per worker = ~112 max (fits in max_connections=100).
# For higher scale: deploy pgbouncer in transaction mode (see deploy/pgbouncer.ini).

# Check for environment files
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$PROJECT_ROOT/scripts/check-env.sh"

if ! check_env_file "$PROJECT_ROOT/.env"; then
    exit 1
fi

source /home/sirobo/papergenerator/.venv/bin/activate
cd /home/sirobo/papergenerator/backend
exec gunicorn --config gunicorn.conf.py "main:app"
