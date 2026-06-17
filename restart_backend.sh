#!/bin/bash
# Kill existing gunicorn processes
pkill -9 -f 'gunicorn.*main:app' 2>/dev/null || true
sleep 2

# Start gunicorn daemon
cd /home/sirobo/papergenerator/backend
.venv/bin/gunicorn -c gunicorn.conf.py main:app --daemon
sleep 3

# Health check
curl -s http://localhost:8001/api/health
