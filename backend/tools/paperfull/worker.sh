#!/bin/bash
# RQ worker entrypoint — run via PM2 as `paper-worker`
source /home/sirobo/papergenerator/.venv/bin/activate
cd /home/sirobo/papergenerator/backend
export PYTHONPATH=/home/sirobo/papergenerator/backend:$PYTHONPATH
exec rq worker --url "${REDIS_URL:-redis://localhost:6379/0}" paper
