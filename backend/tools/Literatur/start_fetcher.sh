#!/bin/bash
# Load env vars
export $(grep -v '^#' /home/sirobo/papergenerator/.env | xargs)

cd /home/sirobo/papergenerator/backend
.venv/bin/python tools/Literatur/bulk_fetch_v2.py --workers 5 2>&1 | tee /tmp/bulk_fetch.log
