"""
Migrate chat_calls logs from old structure to new hourly structure.

Old: backend/tools/chat/data/logs/chat_calls/{paper_id}/{YYYY-MM-DD}.jsonl
New: backend/log/chat/{YYYY-MM-DD-HH}/chat_calls.jsonl

Usage:
    python backend/scripts/migrate_chat_logs.py [--dry-run]
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

OLD_BASE = Path(__file__).parent.parent / "tools" / "chat" / "data" / "logs" / "chat_calls"
NEW_BASE = Path(__file__).parent.parent / "log" / "chat"


def _hourly_path(ts_str):
    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    hour_dir = dt.strftime("%Y-%m-%d-%H")
    return NEW_BASE / hour_dir / "chat_calls.jsonl"


def migrate(dry_run=False):
    if not OLD_BASE.is_dir():
        print(f"Old log directory not found: {OLD_BASE}")
        return

    total_files = 0
    total_lines = 0
    total_skipped = 0

    for paper_dir in sorted(OLD_BASE.iterdir()):
        if not paper_dir.is_dir():
            continue
        paper_id = paper_dir.name
        for jsonl_file in sorted(paper_dir.glob("*.jsonl")):
            total_files += 1
            date_str = jsonl_file.stem
            dest_path = _hourly_path(f"{date_str}T12:00:00+00:00")
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            lines = []
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        total_skipped += 1
                        continue

                    ts = entry.get("ts") or f"{date_str}T00:00:00Z"
                    dest_path = _hourly_path(ts)
                    dest_path.parent.mkdir(parents=True, exist_ok=True)

                    entry.setdefault("correlation_id", f"migrated-{total_lines}")
                    entry.setdefault("paper_id", paper_id)
                    entry["ts"] = ts

                    lines.append((dest_path, json.dumps(entry, ensure_ascii=False)))

            for d_path, line in lines:
                if dry_run:
                    print(f"[DRY-RUN] {d_path} <- {jsonl_file}: {line[:120]}...")
                else:
                    with open(d_path, "a", encoding="utf-8") as f:
                        f.write(line + "\n")

            total_lines += len(lines)

    print(f"Processed {total_files} files, {total_lines} lines, {total_skipped} skipped")
    if dry_run:
        print("Dry-run mode — no files written. Run without --dry-run to execute.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate chat_calls logs to new hourly structure")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing files")
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)
