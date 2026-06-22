#!/usr/bin/env python3
"""PaperFull backend — load .env, bridge slots, exec gunicorn."""
import os, sys
from pathlib import Path

backend = Path("/home/sirobo/papergenerator/backend")
os.chdir(backend)
sys.path.insert(0, str(backend))

from dotenv import load_dotenv
load_dotenv(backend.parent / ".env")
load_dotenv(backend / ".env")

from utils.core.env_loader import normalize_aiotomasi_aliases
try:
    normalize_aiotomasi_aliases()
except Exception as e:
    print(f"WARNING: normalize_aiotomasi_aliases failed: {e}", file=sys.stderr)

# Verify critical vars
for v in ("MODELCHAT1", "AIOTOMASI_API", "AIOTOMASI_APIKEY"):
    if not os.getenv(v):
        print(f"WARNING: {v} not set!", file=sys.stderr)

# Exec gunicorn, replacing current process
gunicorn = str(backend / ".venv/bin/gunicorn")
python = str(backend / ".venv/bin/python3")

os.execve(python, [
    python,
    gunicorn,
    "--config", "gunicorn.conf.py",
    "main:app",
], os.environ)