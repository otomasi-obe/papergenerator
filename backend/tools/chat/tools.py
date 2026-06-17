"""
Chat tools — parsing completion, extracting operations, applying to paper.
Handles thinking/reasoning streams and [APPLY_PAPER] tag processing.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone

from database.models import Paper, db, safe_commit

log = logging.getLogger(__name__)


def parse_completion(text: str) -> dict:
    """Parse AI completion text and extract [APPLY_PAPER] and [ASK_USER] tags.

    Returns:
        {
            "operations": [...],  # list of parsed APPLY_PAPER operations
            "ask_user": {...} | None,  # parsed ASK_USER data if present
            "cleaned_text": "...",  # text with tags removed
            "has_operations": bool,
            "has_ask_user": bool,
        }
    """
    # ── Brace-counting JSON extractor ────────────────────────────────────
    def _extract_tagged_json(text: str, tag: str) -> list[str]:
        """Extract JSON objects between [TAG]...[/TAG] using brace counting.

        Handles nested braces inside JSON (which .*? regex breaks on).
        Returns list of raw JSON strings found.
        """
        start_tag = f'[{tag}]'
        results = []
        search_from = 0
        while True:
            idx = text.find(start_tag, search_from)
            if idx == -1:
                break
            json_start = idx + len(start_tag)
            brace_start = text.find('{', json_start)
            if brace_start == -1:
                break
            depth = 0
            in_string = False
            escape = False
            found = False
            for i in range(brace_start, len(text)):
                ch = text[i]
                if escape:
                    escape = False
                    continue
                if ch == '\\':
                    escape = True
                    continue
                if ch == '"' and not escape:
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        results.append(text[brace_start:i+1])
                        search_from = i + 1
                        found = True
                        break
            if not found:
                break
        return results

    # Parse [APPLY_PAPER]
    apply_matches = _extract_tagged_json(text, 'APPLY_PAPER')
    operations = []

    def _fix_json_escapes(raw: str) -> str:
        """AI puts LaTeX \\frac, \\times, \\beta etc. inside JSON strings.
        \\f, \\t, \\b are invalid JSON escapes → json.loads crashes.
        Even valid ones like \\t (tab), \\b (backspace) corrupt LaTeX.
        Fix: escape ALL bare backslashes followed by letters, preserving
        only legitimate JSON escapes (\\\\ and \\\")."""
        # Strategy: double every backslash that is NOT part of \\\\ or \\"
        # This turns \\frac → \\\\frac, \\times → \\\\times, \\n → \\\\n
        # After JSON parse: \\\\frac → \\frac (literal), which is correct.
        return re.sub(r'\\(?![\\"])', r'\\\\', raw)

    for match in apply_matches:
        try:
            op = json.loads(match)
            if isinstance(op, dict) and op.get("action"):
                operations.append(op)
        except json.JSONDecodeError as e:
            # Retry with escaped backslashes (common LaTeX-in-JSON issue)
            try:
                fixed = _fix_json_escapes(match)
                op = json.loads(fixed)
                if isinstance(op, dict) and op.get("action"):
                    operations.append(op)
                    log.info("Recovered APPLY_PAPER via backslash escaping: %s", op.get("action"))
            except json.JSONDecodeError as e2:
                log.warning("Failed to parse APPLY_PAPER JSON: %s | Error: %s", match[:200], e2)

    # Fallback: handle truncated [APPLY_PAPER] blocks (missing closing tag)
    # This happens when AI runs out of tokens mid-output
    if not operations:
        truncated_pattern = r"\[APPLY_PAPER\]\s*(\{.*?)(?:\[/APPLY_PAPER\]|$)"
        truncated_matches = re.findall(truncated_pattern, text, re.DOTALL)
        for match in truncated_matches:
            # Try to find the complete JSON object by counting braces
            brace_count = 0
            end_idx = 0
            in_string = False
            escape_next = False
            for i, char in enumerate(match):
                if escape_next:
                    escape_next = False
                    continue
                if char == '\\':
                    escape_next = True
                    continue
                if char == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i + 1
                        break
            if end_idx > 0:
                partial_json = match[:end_idx]
                try:
                    op = json.loads(partial_json)
                    if isinstance(op, dict) and op.get("action"):
                        operations.append(op)
                        log.info("Recovered truncated APPLY_PAPER: %s", op.get("action"))
                except json.JSONDecodeError as e:
                    log.warning("Failed to parse truncated APPLY_PAPER: %s | Error: %s", partial_json[:200], e)

    # Parse [ASK_USER] — same brace-counting approach
    ask_matches = _extract_tagged_json(text, 'ASK_USER')
    ask_user = None

    for match in ask_matches:
        try:
            data = json.loads(match)
            if isinstance(data, dict) and data.get("question"):
                ask_user = data
                break  # Only first one
        except json.JSONDecodeError as e:
            log.warning("Failed to parse ASK_USER JSON: %s | Error: %s", match[:200], e)

    # Clean text: remove all [APPLY_PAPER]...[/APPLY_PAPER] and [ASK_USER]...[/ASK_USER] blocks
    # Use greedy-but-bounded regex for cleanup (brace-counting above handles extraction)
    cleaned = re.sub(r"\[APPLY_PAPER\].*?\[/APPLY_PAPER\]", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"\[ASK_USER\].*?\[/ASK_USER\]", "", cleaned, flags=re.DOTALL).strip()

    return {
        "operations": operations,
        "ask_user": ask_user,
        "cleaned_text": cleaned,
        "has_operations": len(operations) > 0,
        "has_ask_user": ask_user is not None,
    }


def _norm_title(s) -> str:
    """Normalize a section title for tolerant matching: lowercase, collapse
    whitespace, strip leading roman/numeric prefixes ("I. ", "1.", "BAB II ")."""
    if not isinstance(s, str):
        return ""
    t = s.strip().lower()
    # strip common heading prefixes the AI or template may add
    t = re.sub(r"^(bab|section|bagian)\s+", "", t)
    t = re.sub(r"^[ivxlcdm]+[\.\)]\s*", "", t)   # roman numerals: "ii. "
    t = re.sub(r"^\d+[\.\)]\s*", "", t)          # arabic: "2. "
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _section_titles(sec: dict) -> list[str]:
    """All title-ish fields a section may carry."""
    return [v for v in (sec.get("title"), sec.get("heading")) if isinstance(v, str)]


def _find_section(sections: list, target: str):
    """Locate a section by title with tolerant matching. Searches top-level
    sections then their subsections. Returns the matching dict or None.

    Matching tiers: exact → case-insensitive → normalized (prefix-stripped) →
    substring. This is what makes chat 'apply to section X' actually land
    instead of failing with 'section not found' on a casing/prefix mismatch.
    """
    if not isinstance(sections, list) or not target:
        return None
    tnorm = _norm_title(target)
    tlow = target.strip().lower()

    def _scan(level):
        # exact
        for s in level:
            if isinstance(s, dict) and target in _section_titles(s):
                return s
        # case-insensitive
        for s in level:
            if isinstance(s, dict) and any(t.strip().lower() == tlow for t in _section_titles(s)):
                return s
        # normalized (strip numbering/prefix)
        for s in level:
            if isinstance(s, dict) and any(_norm_title(t) == tnorm for t in _section_titles(s)):
                return s
        # substring (last resort, only if target is non-trivial)
        if len(tnorm) >= 4:
            for s in level:
                if isinstance(s, dict) and any(tnorm in _norm_title(t) for t in _section_titles(s)):
                    return s
        return None

    hit = _scan([s for s in sections if isinstance(s, dict)])
    if hit:
        return hit
    # search subsections
    for s in sections:
        if isinstance(s, dict) and isinstance(s.get("subsections"), list):
            sub = _scan([ss for ss in s["subsections"] if isinstance(ss, dict)])
            if sub:
                return sub
    return None


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
                sec = _find_section(data.get("sections", []), target)
                if sec is not None:
                    if isinstance(content, str):
                        sec["content"] = [{"id": "text", "text": content}]
                    elif isinstance(content, list):
                        sec["content"] = content
                    results.append(f"✓ Section '{target}' updated")
                else:
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
                tnorm = _norm_title(target)
                tlow = target.strip().lower()

                def _keep(s):
                    if not isinstance(s, dict):
                        return True
                    for t in _section_titles(s):
                        if t == target or t.strip().lower() == tlow or _norm_title(t) == tnorm:
                            return False
                    return True

                data["sections"] = [s for s in sections if _keep(s)]
                if len(data["sections"]) < before:
                    results.append(f"✓ Section '{target}' deleted")
                else:
                    errors.append(f"✗ Section '{target}' not found")

            elif action == "update_keywords":
                if isinstance(content, list):
                    data["keywords"] = [str(k).strip() for k in content if str(k).strip()]
                    results.append(f"✓ Keywords updated ({len(data['keywords'])} items)")
                elif isinstance(content, str):
                    data["keywords"] = [k.strip() for k in content.split(",") if k.strip()]
                    results.append(f"✓ Keywords updated ({len(data['keywords'])} items)")
                else:
                    errors.append("✗ Invalid keywords format (array or comma string)")

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
        safe_commit()
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

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        recv_file = os.path.join(base_dir, f"{timestamp}-recv.json")

        # Check if file already exists (from same timestamp)
        if os.path.exists(recv_file):
            with open(recv_file, "r", encoding="utf-8") as f:
                existing = json.load(f)
        else:
            existing = {
                "message_id": message_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
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

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        recv_file = os.path.join(base_dir, f"{timestamp}-recv.json")

        # Check if file exists (thinking might have been saved already)
        if os.path.exists(recv_file):
            with open(recv_file, "r", encoding="utf-8") as f:
                existing = json.load(f)
        else:
            existing = {
                "message_id": message_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
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
