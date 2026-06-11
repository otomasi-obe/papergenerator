"""
Chat tools — parsing completion, extracting operations, applying to paper.
Handles thinking/reasoning streams and [APPLY_PAPER] tag processing.
"""

import json
import logging
import os
import re
from datetime import datetime

from database.models import Paper, db

log = logging.getLogger(__name__)


def parse_completion(text: str) -> dict:
    """Parse AI completion text and extract [APPLY_PAPER] operations.

    Returns:
        {
            "operations": [...],  # list of parsed JSON operations
            "cleaned_text": "...",  # text with [APPLY_PAPER] tags removed
            "has_operations": bool
        }
    """
    pattern = r"\[APPLY_PAPER\]\s*(\{.*?\})\s*\[/APPLY_PAPER\]"
    matches = re.findall(pattern, text, re.DOTALL)
    operations = []

    for match in matches:
        try:
            op = json.loads(match)
            if isinstance(op, dict) and op.get("action"):
                operations.append(op)
        except json.JSONDecodeError as e:
            log.warning("Failed to parse APPLY_PAPER JSON: %s | Error: %s", match[:200], e)

    # Clean text: remove all [APPLY_PAPER]...[/APPLY_PAPER] blocks
    cleaned = re.sub(pattern, "", text, flags=re.DOTALL).strip()

    return {
        "operations": operations,
        "cleaned_text": cleaned,
        "has_operations": len(operations) > 0,
    }


def apply_operations(paper_id: str, operations: list[dict]) -> dict:
    """Apply [APPLY_PAPER] operations to Paper.data in database.

    Returns:
        {
            "success": bool,
            "results": [...],  # list of status messages per operation
            "errors": [...]
        }
    """
    paper = Paper.query.get(paper_id)
    if not paper:
        return {"success": False, "results": [], "errors": ["Paper not found"]}

    if not isinstance(paper.data, dict):
        paper.data = {}

    data = paper.data
    results = []
    errors = []

    for op in operations:
        action = op.get("action", "")
        target = op.get("target", "")
        content = op.get("content", "")

        try:
            if action == "update_title":
                data["title"] = content
                paper.title = content
                results.append(f"✓ Title updated: {content[:60]}")

            elif action == "update_abstract":
                data["abstract"] = content
                results.append("✓ Abstract updated")

            elif action == "update_section":
                sections = data.get("sections", [])
                found = False
                for sec in sections:
                    if isinstance(sec, dict) and (
                        sec.get("title") == target or sec.get("heading") == target
                    ):
                        if isinstance(content, str):
                            sec["content"] = [{"id": "text", "text": content}]
                        elif isinstance(content, list):
                            sec["content"] = content
                        found = True
                        results.append(f"✓ Section '{target}' updated")
                        break
                if not found:
                    errors.append(f"✗ Section '{target}' not found")

            elif action == "add_section":
                if "sections" not in data or not isinstance(data["sections"], list):
                    data["sections"] = []
                new_sec = {
                    "title": target,
                    "content": (
                        [{"id": "text", "text": content}]
                        if isinstance(content, str)
                        else content
                    ),
                }
                data["sections"].append(new_sec)
                results.append(f"✓ Section '{target}' added")

            elif action == "delete_section":
                sections = data.get("sections", [])
                before = len(sections)
                data["sections"] = [
                    s
                    for s in sections
                    if not (
                        isinstance(s, dict)
                        and (s.get("title") == target or s.get("heading") == target)
                    )
                ]
                if len(data["sections"]) < before:
                    results.append(f"✓ Section '{target}' deleted")
                else:
                    errors.append(f"✗ Section '{target}' not found")

            elif action == "update_references":
                if isinstance(content, list):
                    data["references"] = content
                    results.append(f"✓ References updated ({len(content)} items)")
                else:
                    errors.append("✗ Invalid references format (must be array)")

            else:
                errors.append(f"✗ Unknown action: {action}")

        except Exception as e:
            log.exception("Error applying operation %s: %s", action, e)
            errors.append(f"✗ Error in {action}: {str(e)[:100]}")

    # Commit to database
    try:
        # Assign a fresh copy so SQLAlchemy detects the mutation,
        # then also call flag_modified as belt+suspenders for JSONB.
        paper.data = dict(data)
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(paper, "data")
        db.session.commit()
    except Exception as e:
        log.exception("Failed to commit paper changes: %s", e)
        db.session.rollback()
        return {
            "success": False,
            "results": results,
            "errors": errors + [f"Database commit failed: {str(e)}"],
        }

    return {
        "success": len(errors) == 0,
        "results": results,
        "errors": errors,
    }


def save_thinking_to_fs(
    username: str, paper_id: str, conv_id: str, thinking_text: str, message_id: str
) -> bool:
    """Save thinking/reasoning text to filesystem recv.json.

    Appends thinking as a separate field in the recv.json structure.
    """
    try:
        base_dir = f"/home/sirobo/papergenerator/backend/user/{username}/{paper_id}/chat/{conv_id}"
        os.makedirs(base_dir, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        recv_file = os.path.join(base_dir, f"{timestamp}-recv.json")

        # Check if file already exists (from same timestamp)
        if os.path.exists(recv_file):
            with open(recv_file, "r", encoding="utf-8") as f:
                existing = json.load(f)
        else:
            existing = {
                "message_id": message_id,
                "timestamp": datetime.utcnow().isoformat(),
            }

        # Add thinking field
        existing["thinking"] = thinking_text

        with open(recv_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)

        return True
    except Exception as e:
        log.warning("Failed to save thinking to filesystem: %s", e)
        return False


def append_completion_to_recv(
    username: str,
    paper_id: str,
    conv_id: str,
    completion_text: str,
    message_id: str,
    operations: list = None,
) -> bool:
    """Append completion text and operations to recv.json.

    If file already exists (thinking was saved), update it.
    Otherwise create new file.
    """
    try:
        base_dir = f"/home/sirobo/papergenerator/backend/user/{username}/{paper_id}/chat/{conv_id}"
        os.makedirs(base_dir, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        recv_file = os.path.join(base_dir, f"{timestamp}-recv.json")

        # Check if file exists (thinking might have been saved already)
        if os.path.exists(recv_file):
            with open(recv_file, "r", encoding="utf-8") as f:
                existing = json.load(f)
        else:
            existing = {
                "message_id": message_id,
                "timestamp": datetime.utcnow().isoformat(),
            }

        # Add completion and operations
        existing["completion"] = completion_text
        if operations:
            existing["operations"] = operations

        with open(recv_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)

        return True
    except Exception as e:
        log.warning("Failed to save completion to filesystem: %s", e)
        return False
