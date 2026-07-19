#!/usr/bin/env python3
"""Wrapper to run image generation worker with correct Python path."""
import sys
import os

# Add backend directory to path
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, backend_dir)

# Load .env
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(backend_dir) / ".env", override=True)
load_dotenv(Path(backend_dir) / "tools" / "image_generation" / ".env", override=True)

# Now import and run the worker
from tools.image_generation.worker import main

if __name__ == "__main__":
    main()
