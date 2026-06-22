#!/usr/bin/env python3
"""PaperFull backend launcher — loads .env then starts gunicorn."""

import os, sys, subprocess
from pathlib import Path
from dotenv import load_dotenv

# Chdir to backend directory
backend_dir = Path("/home/sirobo/papergenerator/backend")
os.chdir(backend_dir)

# Load both .env files (no override — respect explicitly-set vars)
load_dotenv(backend_dir.parent / ".env")
load_dotenv(backend_dir / ".env")

# Bridge AIOTOMASI_API1 → AIOTOMASI_API, etc.
from utils.core.env_loader import normalize_aiotomasi_aliases
try:
    normalize_aiotomasi_aliases()
except Exception:
    pass

# Verify critical vars
for v in ("AIOTOMASI_API", "AIOTOMASI_APIKEY", "MODELCHAT1"):
    if not os.getenv(v):
        print(f"WARNING: {v} not set in environment", file=sys.stderr)

# Start gunicorn
venv_python = backend_dir / "venv" / "bin" / "python"
gunicorn = backend_dir / "venv" / "bin" / "gunicorn"
os.execv(str(venv_python), [
    str(venv_python),
    str(gunicorn),
    "--config", "gunicorn.conf.py",
    "main:app",
])