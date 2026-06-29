"""
Migrate files from centralized data/{charts,exports,uploads}/* to per-user dirs.

New structure:
    user/<user_id>/charts/<paper_id>/
    user/<user_id>/exports/
    user/<user_id>/uploads/<paper_id>/

Run from backend/:  python -m scripts.migrate_to_per_user_dirs
"""

import logging
import os
import shutil
import sys
from pathlib import Path

# Ensure backend dir is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

# Base paths
BACKEND = Path(__file__).resolve().parent.parent
LEGACY_CHARTS = BACKEND / "data" / "charts"
LEGACY_EXPORTS = BACKEND / "data" / "exports"
LEGACY_UPLOADS = BACKEND / "data" / "uploads"
USER_BASE = BACKEND / "user"


def get_user_id_from_db(paper_id: str):
    """Query DB for user_id given a paper_id. Returns None on failure."""
    try:
        from utils.database.models import Paper
        paper = Paper.query.filter_by(id=paper_id).first()
        if paper:
            return paper.user_id
        return None
    except Exception as e:
        log.warning("Could not query paper %s: %s", paper_id, e)
        return None


def migrate_charts():
    """Move data/charts/<paper_id>/ → user/<user_id>/charts/<paper_id>/"""
    if not LEGACY_CHARTS.exists():
        log.info("No legacy charts dir at %s", LEGACY_CHARTS)
        return 0
    count = 0
    for paper_dir in sorted(LEGACY_CHARTS.iterdir()):
        if not paper_dir.is_dir():
            continue
        paper_id = paper_dir.name
        user_id = get_user_id_from_db(paper_id)
        if user_id is None:
            log.warning("SKIP charts/%s — no user_id found in DB", paper_id)
            continue
        target = USER_BASE / str(user_id) / "charts" / paper_id
        target.mkdir(parents=True, exist_ok=True)
        for f in paper_dir.iterdir():
            if f.is_file():
                shutil.copy2(str(f), str(target / f.name))
        log.info("Copied charts/%s (%d files) → user/%s/charts/%s/",
                 paper_id, len(list(paper_dir.iterdir())), user_id, paper_id)
        count += 1
    return count


def migrate_exports():
    """Move data/exports/<file>.docx → user/<user_id>/exports/<file>"""
    if not LEGACY_EXPORTS.exists():
        log.info("No legacy exports dir at %s", LEGACY_EXPORTS)
        return 0
    count = 0
    for f in sorted(LEGACY_EXPORTS.iterdir()):
        if not f.is_file():
            continue
        # Exports don't have paper_id in their name reliably.
        # We copy to user/0/exports/ as unclaimed, manually assignable.
        target = USER_BASE / "0" / "exports"
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(f), str(target / f.name))
        count += 1
    log.info("Copied %d exports to user/0/exports/ (unclaimed — assign manually)", count)
    return count


def migrate_uploads():
    """Move data/uploads/<paper_id>/ → user/<user_id>/uploads/<paper_id>/"""
    if not LEGACY_UPLOADS.exists():
        log.info("No legacy uploads dir at %s", LEGACY_UPLOADS)
        return 0
    count = 0
    for paper_dir in sorted(LEGACY_UPLOADS.iterdir()):
        if not paper_dir.is_dir():
            continue
        paper_id = paper_dir.name
        user_id = get_user_id_from_db(paper_id)
        if user_id is None:
            log.warning("SKIP uploads/%s — no user_id found in DB", paper_id)
            continue
        target = USER_BASE / str(user_id) / "uploads" / paper_id
        target.mkdir(parents=True, exist_ok=True)
        for f in paper_dir.iterdir():
            if f.is_file():
                shutil.copy2(str(f), str(target / f.name))
        log.info("Copied uploads/%s → user/%s/uploads/%s/", paper_id, user_id, paper_id)
        count += 1
    return count


def main():
    log.info("=== Migrating to per-user directories ===")

    # Init DB connection (requires Flask app context)
    try:
        from main import app
        with app.app_context():
            c = migrate_charts()
            e = migrate_exports()
            u = migrate_uploads()
            log.info("Done. Migrated %d chart dirs, %d exports, %d upload dirs.", c, e, u)
    except Exception as ex:
        log.error("Migration failed: %s", ex)
        log.info("Try running with: cd backend && FLASK_APP=main.py python -m scripts.migrate_to_per_user_dirs")
        sys.exit(1)


if __name__ == "__main__":
    main()