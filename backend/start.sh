#!/bin/bash
# Production startup: Gunicorn gthread workers (sync + threads)
# 5 workers × 4 threads = 20 concurrent requests, nginx queues the rest

# Check for environment files
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$PROJECT_ROOT/scripts/check-env.sh"

if ! check_env_file "$PROJECT_ROOT/.env"; then
    exit 1
fi

source /home/sirobo/papergenerator/.venv/bin/activate
cd /home/sirobo/papergenerator/backend
exec gunicorn --config gunicorn.conf.py "main:app"
