#!/bin/bash
# Production startup: Gunicorn gthread workers (sync + threads)
# 16 workers × 8 threads = 128 concurrent request slots.

cd /home/sirobo/papergenerator/backend

# Load env from project root
if [ -f /home/sirobo/papergenerator/.env ]; then
    export $(grep -v '^#' /home/sirobo/papergenerator/.env | xargs)
fi

# Use venv Python directly (no activation needed)
exec /home/sirobo/papergenerator/backend/.venv/bin/python -m gunicorn --config gunicorn.conf.py "main:app"
