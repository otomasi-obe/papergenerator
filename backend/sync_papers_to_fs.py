#!/usr/bin/env python3
"""Sync ALL papers from PostgreSQL database to filesystem user storage.

Writes each paper as:
  backend/user/<username>/<paper_id>/<paper_id>.json

Where <username> = safe(email.split('@')[0])

Skips papers whose JSON already exists and is valid.
"""

import os, json, uuid, sys, re
from datetime import datetime, timezone

os.environ['DATABASE_URL'] = 'postgresql://papergenerator:PaperGen2026!Secure@localhost:5432/papergenerator'

parent = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, parent)

from flask import Flask
from database.models import db, Paper, User

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

USER_BASE = os.path.join(parent, 'user')
SAFE_RE = re.compile(r'[^A-Za-z0-9._-]+')

def safe(name, fallback="unknown"):
    s = SAFE_RE.sub("_", str(name or "")).strip("._-")
    return s or fallback

def username_from_email(email):
    return safe(email.split("@")[0])

with app.app_context():
    # Get all papers with user email in one query
    results = db.session.query(Paper, User).join(User, Paper.user_id == User.id).order_by(User.email, Paper.created_at).all()

    total = len(results)
    written = 0
    skipped = 0
    errors = 0

    print(f"Total papers to sync: {total}")
    print()

    for paper, user in results:
        email = user.email
        uname = username_from_email(email)
        paper_id = paper.id
        title = paper.title

        # Target directory: backend/user/<username>/<paper_id>/
        paper_dir = os.path.join(USER_BASE, uname, paper_id)
        json_path = os.path.join(paper_dir, f"{paper_id}.json")

        # Skip if already exists and has content
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
                if existing.get('paper_data') or existing.get('judul'):
                    skipped += 1
                    continue
            except Exception:
                pass  # Re-write if corrupt

        # Ensure directory exists
        os.makedirs(paper_dir, exist_ok=True)

        # Build payload
        paper_data = paper.data or {}
        if not isinstance(paper_data, dict):
            paper_data = {}

        payload = {
            "paper_id": paper_id,
            "title": title,
            "updated_at": paper.updated_at.isoformat() if paper.updated_at else datetime.now(timezone.utc).isoformat(),
            "paper_data": paper_data,
        }

        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            written += 1
            if written % 20 == 0 or written <= 5:
                print(f"  [{written}/{total}] {uname}/{paper_id} — {title[:60]}")
        except Exception as e:
            errors += 1
            print(f"  ERROR: {uname}/{paper_id}: {e}")

    print()
    print(f"Done: {written} written, {skipped} skipped (already exist), {errors} errors")
    print(f"Total in DB: {total}")

    # Summary by user
    print()
    print("--- Filesystem summary ---")
    for d in sorted(os.listdir(USER_BASE)):
        user_dir = os.path.join(USER_BASE, d)
        if not os.path.isdir(user_dir):
            continue
        count = sum(1 for _ in os.listdir(user_dir) if os.path.isdir(os.path.join(user_dir, _)))
        print(f"  {d}: {count} paper dirs")
