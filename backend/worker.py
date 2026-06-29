#!/usr/bin/env python3
"""RQ Worker wrapper for PM2 management."""
import sys
import os

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env files (mirrors main.py so REDIS_URL picks up the password)
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

from redis import Redis
from rq import Worker, Queue

# Use same Redis config as the app
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
conn = Redis.from_url(redis_url)

# Listen to the 'paper' queue
queues = [Queue("paper", connection=conn)]

if __name__ == "__main__":
    w = Worker(queues, connection=conn)
    w.work()
