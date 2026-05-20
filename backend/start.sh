#!/bin/bash
# Production startup: Gunicorn gthread workers (sync + threads)
# 5 workers × 4 threads = 20 concurrent requests, nginx queues the rest
source /home/sirobo/papergenerator/.venv/bin/activate
cd /home/sirobo/papergenerator/backend
exec gunicorn --config gunicorn.conf.py "app:app"
