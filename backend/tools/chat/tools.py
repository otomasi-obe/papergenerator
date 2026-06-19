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

# ── Paper Data Normalization ──────────────────────────────────────────────
# Paperfull generator outputs keyed sections: section1, section2, ...
# Chat tools expect a "sections" array. Normalize on read & write.


def normalize_paper_to_array(data: dict) -> dict:
    """Convert keyed sections (section1, section2, ...) to a 'sections' array.

    Also normalizes references from section-like object or {items: [...]} to flat array.
    Modifies data in-place. Returns same dict.
    """
    if not isinstance(data, dict):
        return data

    # Already has populated sections array → skip
    if "sections" in data and isinstance(data["sections"], list) and len(data["sections"]) > 0:
        # Still normalize references if needed
        _normalize_references(data)
        return data

    # Build sections array from keyed entries
    sections = []
    section_keys = []
    for key in sorted(data.keys()):
        m = re.match(r'^section(\d+)([a-z])?$', key)
        if m:
            sec = data[key]
            if isinstance(sec, dict):
                # Ensure title exists (some old data uses "heading")
                if "title" not in sec:
                    if "heading" in sec:
                        sec["title"] = sec["heading"]
                    else:
                        sec["title"] = key.replace("section", "Section ").upper()
                sections.append(sec)
                section_keys.append(key)

    if sections:
        data["sections"] = sections
        data["_section_keys"] = section_keys  # for write-back

    _normalize_references(data)
    return data


def _normalize_references(data: dict):
    """Normalize references to flat array if stored as object."""
    refs = data.get("references")
    if isinstance(refs, dict):
        if "items" in refs and isinstance(refs["items"], list):
            data["references"] = refs["items"]
        elif "content" in refs and isinstance(refs["content"], list):
            data["references"] = refs["content"]


def _writeback_sections(data: dict):
    """After editing via sections array, write changes back to keyed entries.
    
    Handles: updates, adds (new sections beyond original count), deletes (removes orphaned keys).
    """
    section_keys = data.pop("_section_keys", None)
    new_sections = data.get("sections")
    if not isinstance(new_sections, list):
        return
    
    # Build complete set of section-pattern keys to clean up
    all_section_keys = [k for k in data.keys() if re.match(r'^section\d+[a-z]?$', k)]
    # Track which keys are assigned in the new mapping
    used_keys = set()
    
    if section_keys:
        # Map each existing section array entry back to its original key
        for i, key in enumerate(section_keys):
            if i < len(new_sections):
                data[key] = new_sections[i]
                used_keys.add(key)
            else:
                # Section was deleted — remove key
                data.pop(key, None)
        # Handle new sections added beyond original count
        next_num = len(section_keys) + 1
        for i in range(len(section_keys), len(new_sections)):
            # Find available slot (skip keys that still exist)
            while f"section{next_num}" in data:
                next_num += 1
            new_key = f"section{next_num}"
            data[new_key] = new_sections[i]
            used_keys.add(new_key)
            next_num += 1
    else:
        # No original keys — create from scratch
        for i, sec in enumerate(new_sections, 1):
            key = f"section{i}"
            data[key] = sec
            used_keys.add(key)
    
    # Clean up orphaned section keys not used in the new mapping
    for key in all_section_keys:
        if key not in used_keys:
            data.pop(key, None)
    
    # Remove the temporary sections array (keyed format doesn't use it)
    data.pop("sections", None)


def parse_completion(text: str) -> dict:
    """Parse AI completion text and extract [APPLY_PAPER], [ASK_USER], [GENERATE_DOCX] tags.

    Returns:
        {
            "operations": [...],  # list of parsed APPLY_PAPER operations
            "ask_user": {...} | None,  # parsed ASK_USER data if present
            "docx_spec": {...} | None,  # parsed GENERATE_DOCX spec if present
            "cleaned_text": "...",  # text with tags removed
            "has_operations": bool,
            "has_ask_user": bool,
            "has_docx": bool,
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
            parsed = json.loads(match)
        except json.JSONDecodeError as e:
            # Retry with escaped backslashes (common LaTeX-in-JSON issue)
            try:
                parsed = json.loads(_fix_json_escapes(match))
                log.info("Recovered APPLY_PAPER via backslash escaping: %d items", len(parsed) if isinstance(parsed, list) else 1)
            except json.JSONDecodeError as e2:
                log.warning("Failed to parse APPLY_PAPER JSON: %s | Error: %s", match[:200], e2)
                continue

        # Support both single object and array of objects
        items = [parsed] if isinstance(parsed, dict) else parsed if isinstance(parsed, list) else []
        for op in items:
            if isinstance(op, dict) and op.get("action"):
                operations.append(op)

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
                    parsed = json.loads(partial_json)
                    items = [parsed] if isinstance(parsed, dict) else parsed if isinstance(parsed, list) else []
                    for op in items:
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

    # Parse [GENERATE_DOCX] — same brace-counting approach
    docx_spec = None
    docx_matches = _extract_tagged_json(text, 'GENERATE_DOCX')
    for match in docx_matches:
        try:
            data = json.loads(match)
            if isinstance(data, dict):
                docx_spec = data
                break
        except json.JSONDecodeError as e:
            # Retry with escaped backslashes (same as APPLY_PAPER)
            try:
                fixed = _fix_json_escapes(match)
                data = json.loads(fixed)
                if isinstance(data, dict):
                    docx_spec = data
                    break
            except json.JSONDecodeError as e2:
                log.warning("Failed to parse GENERATE_DOCX JSON: %s | Error: %s", match[:200], e2)

    # Clean text: remove all [APPLY_PAPER]...[/APPLY_PAPER], [ASK_USER]...[/ASK_USER],
    # and [GENERATE_DOCX]...[/GENERATE_DOCX] blocks
    # Use greedy-but-bounded regex for cleanup (brace-counting above handles extraction)
    cleaned = re.sub(r"\[APPLY_PAPER\].*?\[/APPLY_PAPER\]", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"\[ASK_USER\].*?\[/ASK_USER\]", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"\[GENERATE_DOCX\].*?\[/GENERATE_DOCX\]", "", cleaned, flags=re.DOTALL).strip()

    return {
        "operations": operations,
        "ask_user": ask_user,
        "docx_spec": docx_spec,
        "cleaned_text": cleaned,
        "has_operations": len(operations) > 0,
        "has_ask_user": ask_user is not None,
        "has_docx": docx_spec is not None,
    }


def _norm_title(s) -> str:
    """Normalize a section title for tolerant matching: lowercase, collapse
    whitespace, strip leading roman/numeric prefixes ("I. ", "1.", "BAB II ")."""
    if not isinstance(s, str):
        return ""
    t = s.strip()
    if not t:  # whitespace-only / empty → no match possible
        return ""
    t = t.lower()
    # strip common heading prefixes the AI or template may add
    t = re.sub(r"^(bab|section|bagian)\s+", "", t)
    # Strip Roman numeral prefix (I–XXX) with delimiter (dot/paren/space)
    # Known set prevents false matches on words like "introduction", "mixed", "diskusi"
    _ROMANS = {'i','ii','iii','iv','v','vi','vii','viii','ix','x',
               'xi','xii','xiii','xiv','xv','xvi','xvii','xviii','xix','xx',
               'xxi','xxii','xxiii','xxiv','xxv','xxvi','xxvii','xxviii','xxix','xxx'}
    _m = re.match(r'^([ivxlcdm])([\.\)])\s*', t)  # single char + delimiter
    if _m and _m.group(1) in _ROMANS:
        t = t[_m.end():]
    else:
        _m = re.match(r'^([ivxlcdm]{2,})([\.\)]\s*|\s+)', t)  # 2+ chars + delimiter/space
        if _m and _m.group(1) in _ROMANS:
            t = t[_m.end():]
    t = re.sub(r"^\d+[\.\)]?\s*", "", t)          # arabic: "2.", "2 " (optional dot/paren)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _section_titles(sec: dict) -> list[str]:
    """All title-ish fields a section may carry."""
    return [v for v in (sec.get("title"), sec.get("heading")) if isinstance(v, str)]


def _find_section(sections: list, target: str):
    """Locate a section by title with tolerant matching. Searches top-level
    sections then their subsections. Returns the matching dict or None.

    Matching tiers: exact → case-insensitive → normalized (prefix-stripped) →
    aliased (English↔Indonesian common section names) → substring.
    This is what makes chat 'apply to section X' actually land
    instead of failing with 'section not found' on a casing/prefix mismatch.
    """
    if not isinstance(sections, list) or not target:
        return None
    tnorm = _norm_title(target)
    tlow = target.strip().lower()

    # Section alias map: English ↔ Indonesian common section names
    _ALIASES = {
        "introduction": "pendahuluan",
        "literature review": "tinjauan pustaka",
        "methodology": "metodologi",
        "methods": "metodologi",
        "results and discussion": "hasil dan pembahasan",
        "results": "hasil dan pembahasan",
        "discussion": "hasil dan pembahasan",
        "conclusion": "kesimpulan",
    }
    # Normalize alias keys
    _ALIASES = {_norm_title(k): _norm_title(v) for k, v in _ALIASES.items()}
    # Also add reverse mappings
    for k, v in list(_ALIASES.items()):
        _ALIASES.setdefault(v, k)

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
        # aliased
        alias = _ALIASES.get(tnorm)
        if alias:
            for s in level:
                if isinstance(s, dict) and any(_norm_title(t) == alias for t in _section_titles(s)):
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


def _validate_paper_structure(data: dict) -> list[str]:
    """Validate paper JSON structure after edits. Returns list of error messages.

    Checks:
    - sections is array of dicts with required 'title'
    - section.content (if present) is array of block dicts with 'id' field
    - references (if present) is array of dicts
    """
    errors = []
    sections = data.get("sections")
    if sections is not None:
        if not isinstance(sections, list):
            errors.append("sections must be an array")
        else:
            for i, sec in enumerate(sections):
                if not isinstance(sec, dict):
                    errors.append(f"sections[{i}] must be a dict")
                    continue
                if not sec.get("title"):
                    errors.append(f"sections[{i}] missing 'title'")
                content = sec.get("content")
                if content is not None:
                    if not isinstance(content, list):
                        errors.append(f"sections[{i}].content must be an array")
                    else:
                        for j, block in enumerate(content):
                            if isinstance(block, dict) and not block.get("id"):
                                errors.append(f"sections[{i}].content[{j}] missing 'id'")

    refs = data.get("references")
    if refs is not None:
        if not isinstance(refs, list):
            errors.append("references must be an array")
        else:
            for i, ref in enumerate(refs):
                if not isinstance(ref, dict):
                    errors.append(f"references[{i}] must be a dict (got {type(ref).__name__})")

    return errors


def apply_operations(paper_id: str, operations: list[dict], user_id: int | None = None) -> dict:
    """Apply [APPLY_PAPER] operations to Paper.data in database.

    Args:
        paper_id: Paper ID to modify.
        operations: List of operation dicts (action, target, content).
        user_id: Optional — if provided, paper ownership is verified.

    Returns:
        {
            "success": bool,
            "results": [...],  # list of status messages per operation
            "errors": [...]
        }
    """
    query = Paper.query.filter_by(id=paper_id)
    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    paper = query.first()
    if not paper:
        return {"success": False, "results": [], "errors": ["Paper not found"]}

    if not isinstance(paper.data, dict):
        paper.data = {}

    data = paper.data

    # Normalize keyed sections (section1, section2) → "sections" array for operations
    normalize_paper_to_array(data)

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
                        # Merge: replace text of existing text blocks, append new text block
                        # Preserve non-text blocks (gambar, rumus, tabel, equation)
                        existing = sec.get("content", [])
                        if isinstance(existing, list):
                            new_content = list(existing)  # copy
                            replaced = False
                            for i, block in enumerate(new_content):
                                if isinstance(block, dict) and block.get("id") == "text":
                                    new_content[i] = {"id": "text", "text": content}
                                    replaced = True
                                    break
                            if not replaced:
                                new_content.append({"id": "text", "text": content})
                            sec["content"] = new_content
                        else:
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
                    data["keywords"] = [str(k).strip() for k in content if k is not None and str(k).strip()]
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

    # Validate paper JSON structure BEFORE writeback (sections array still exists)
    validation_errors = _validate_paper_structure(data)
    if validation_errors:
        log.warning("Paper %s validation errors: %s", paper_id, validation_errors)
        for ve in validation_errors:
            errors.append(f"⚠ Validation: {ve}")
        # Still save, but warn — validation is advisory

    # Commit to database
    paper.updated_at = datetime.now(timezone.utc)

    # Write changes back to keyed section format (section1, section2, ...)
    _writeback_sections(data)

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

    # Sync paper.json to filesystem so export/generate reads fresh data
    try:
        from utils.core.user_storage import get_username, save_paper_json_by_id
        _uid = user_id if user_id is not None else paper.user_id
        _uname = get_username(user_id=_uid)
        save_paper_json_by_id(_uname, paper_id, dict(data))
    except Exception as fs_err:
        log.warning("Failed to sync paper.json for %s: %s", paper_id, fs_err)
        # Non-fatal — DB commit succeeded, just filesystem is stale

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
