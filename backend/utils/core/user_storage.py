"""
User Storage System
===================
Penyimpanan data per user sesuai aturan:
  backend/user/<namauser>/<judul_paper>/
    paper.json  - data paper lengkap (selalu update)
    chat/       - log AI per percakapan (chat/{conv_name}/{ts}-{send|recv}.json)
    image/      - generate image + grafik + upload image
    docx/       - export docx
    data/       - data file (CSV, XLSX, dll)
    file/       - uploaded files + extracted text (.txt)
"""

import hashlib
import json
import logging
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

# Base directory
BACKEND_DIR = Path(__file__).parent.parent.parent
USER_BASE = BACKEND_DIR / "user"

_SAFE_RE = re.compile(r'[^A-Za-z0-9._-]+')

def _safe(name, fallback="unknown"):
    s = _SAFE_RE.sub("_", str(name or "")).strip("._-")
    # ponytail: max path segment capped at 200; callers append suffixes/extensions
    if len(s) > 200:
        s = s[:200].strip("._-")
    return s or fallback


def get_safe_dir(user_id, email=None):
    """Return a collision-resistant directory name for a user.

    Combines the sanitized email local-part with a short hash derived from
    user_id so that two users whose emails sanitize to the same string
    (e.g. ``john.doe@…`` vs ``john+doe@…``) get distinct directories (BUG-24).

    Format: ``<sanitized_name>_<8-hex-chars>``
    """
    if email:
        base_name = _safe(email.split("@")[0], "user")
    else:
        base_name = f"user_{user_id}"
    # 8-char hex from SHA-256 of user_id — short enough to be readable,
    # long enough that collisions are astronomically unlikely.
    hash_suffix = hashlib.sha256(str(user_id).encode()).hexdigest()[:8]
    return f"{base_name}_{hash_suffix}"


def get_username(user_id=None, email=None):
    if email:
        return _safe(email.split("@")[0])
    if user_id:
        try:
            from utils.database.models import User
            user = User.query.get(int(user_id))
            if user and user.email:
                return _safe(user.email.split("@")[0])
            return f"user_{user_id}"
        except Exception:
            return f"user_{user_id}"
    return "anonymous"


def _ensure_dir(path):
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_paper_base(username, judul_paper):
    safe_user = _safe(username)
    safe_judul = _safe(judul_paper, "untitled")
    return _ensure_dir(USER_BASE / safe_user / safe_judul)


def get_paper_base_by_id(username, paper_id):
    """Return base dir for paper_id-based storage: user/<paper_id>/"""
    safe_id = _safe(paper_id, "unknown")
    return _ensure_dir(USER_BASE / safe_id)

def save_chat_send_by_id(username, paper_id, data, conv_id=None):
    """Save user→AI message to user/<username>/<paper_id>/chat/<conv_id>/YYYYMMDD-HHMMSS-send.json"""
    base = get_paper_base_by_id(username, paper_id)
    chat_dir = _ensure_dir(base / "chat")
    if conv_id:
        chat_dir = _ensure_dir(chat_dir / _safe(conv_id, "default"))
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filepath = chat_dir / f"{ts}-send.json"
    payload = {"ts": datetime.now(timezone.utc).isoformat(), "direction": "send", **data}
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    log.debug("Saved send chat: %s", filepath)
    return filepath

def save_chat_recv_by_id(username, paper_id, data, conv_id=None):
    """Save AI→user message to user/<username>/<paper_id>/chat/<conv_id>/YYYYMMDD-HHMMSS-recv.json"""
    base = get_paper_base_by_id(username, paper_id)
    chat_dir = _ensure_dir(base / "chat")
    if conv_id:
        chat_dir = _ensure_dir(chat_dir / _safe(conv_id, "default"))
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filepath = chat_dir / f"{ts}-recv.json"
    payload = {"ts": datetime.now(timezone.utc).isoformat(), "direction": "recv", **data}
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    log.debug("Saved recv chat: %s", filepath)
    return filepath


def save_chat_send(username, judul_paper, data, conv_name=None):
    base = get_paper_base(username, judul_paper)
    chat_dir = _ensure_dir(base / "chat")
    if conv_name:
        chat_dir = _ensure_dir(chat_dir / _safe(conv_name, "default"))
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filepath = chat_dir / f"{ts}-send.json"
    payload = {"ts": datetime.now(timezone.utc).isoformat(), "direction": "send", **data}
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return filepath


def save_chat_recv(username, judul_paper, data, conv_name=None):
    base = get_paper_base(username, judul_paper)
    chat_dir = _ensure_dir(base / "chat")
    if conv_name:
        chat_dir = _ensure_dir(chat_dir / _safe(conv_name, "default"))
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    filepath = chat_dir / f"{ts}-recv.json"
    payload = {"ts": datetime.now(timezone.utc).isoformat(), "direction": "recv", **data}
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return filepath


def save_image(username, judul_paper, source_path, filename=None):
    base = get_paper_base(username, judul_paper)
    image_dir = _ensure_dir(base / "image")
    if filename is None:
        filename = Path(source_path).name
    dest = image_dir / _safe(filename)
    shutil.copy2(str(source_path), str(dest))
    return dest


def save_image_bytes(username, judul_paper, data_bytes, filename):
    base = get_paper_base(username, judul_paper)
    image_dir = _ensure_dir(base / "image")
    filepath = image_dir / _safe(filename)
    with open(filepath, "wb") as f:
        f.write(data_bytes)
    return filepath


def get_image_dir(username, judul_paper):
    base = get_paper_base(username, judul_paper)
    return _ensure_dir(base / "image")


def save_docx(username, judul_paper, source_path, template_name):
    base = get_paper_base(username, judul_paper)
    docx_dir = _ensure_dir(base / "Docx")
    ts = datetime.now(timezone.utc).strftime("%H%M%S")
    safe_judul = _safe(judul_paper, "paper")
    filename = f"{template_name}_{ts}_{safe_judul}.docx"
    dest = docx_dir / filename
    shutil.copy2(str(source_path), str(dest))
    return dest


def get_docx_dir(username, judul_paper):
    base = get_paper_base(username, judul_paper)
    return _ensure_dir(base / "Docx")


def save_paper_json(username, judul_paper, paper_data, paper_id=None):
    """Save full paper data as paper.json in user storage.

    When paper_id is provided, saves to user/<username>/<paper_id>/<paper_id>.json.
    """
    if paper_id:
        return save_paper_json_by_id(username, paper_id, paper_data)
    base = get_paper_base(username, judul_paper)
    filepath = base / "paper.json"
    payload = {
        "judul": judul_paper,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "paper_data": {"paper": paper_data},
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    # Remove old judulpaper.json if exists
    old_path = base / "judulpaper.json"
    if old_path.exists():
        try:
            old_path.unlink()
        except Exception:
            pass
    return filepath


def save_paper_json_by_id(username, paper_id, paper_data):
    """Save paper data to user/<username>/<paper_id>/<paper_id>.json."""
    base = get_paper_base_by_id(username, paper_id)
    filepath = base / f"{_safe(paper_id, 'paper')}.json"
    payload = {
        "paper_id": paper_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "paper_data": {"paper": paper_data},
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return filepath


def get_paper_json(username, judul_paper):
    """Read paper.json from user storage."""
    return get_judul_paper(username, judul_paper)


def save_data(username, judul_paper, source_path, filename=None):
    """Save a data file (CSV, XLSX, etc.) to data/ directory."""
    base = get_paper_base(username, judul_paper)
    data_dir = _ensure_dir(base / "data")
    if filename is None:
        filename = Path(source_path).name
    dest = data_dir / _safe(filename)
    shutil.copy2(str(source_path), str(dest))
    return dest


def save_data_bytes(username, judul_paper, data_bytes, filename):
    """Save data bytes to data/ directory."""
    base = get_paper_base(username, judul_paper)
    data_dir = _ensure_dir(base / "data")
    filepath = data_dir / _safe(filename)
    with open(filepath, "wb") as f:
        f.write(data_bytes)
    return filepath


def get_data_dir(username, judul_paper):
    """Get data directory path."""
    base = get_paper_base(username, judul_paper)
    return _ensure_dir(base / "data")


def save_file_as_txt(username, judul_paper, text_content, filename):
    """Save extracted text content as .txt file in file/ directory.

    If a file with the same name already exists, it is overwritten (no
    ``_1`` duplicates) because extracted text from the same source is
    idempotent.
    """
    base = get_paper_base(username, judul_paper)
    file_dir = _ensure_dir(base / "file")
    txt_name = Path(filename).stem + ".txt"
    safe_name = _safe(txt_name)
    filepath = file_dir / safe_name
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(text_content)
    return filepath


def save_uploaded_file(username, judul_paper, source_path, filename):
    base = get_paper_base(username, judul_paper)
    file_dir = _ensure_dir(base / "file")
    safe_name = _safe(filename)
    dest = file_dir / safe_name
    if dest.exists():
        # BUG FIX: Counter loop was not re-sanitizing the incremented filename,
        # allowing collisions with sanitized names to create unpredictable paths.
        stem = Path(filename).stem  # Use original (unsanitized) stem for counter
        suffix = Path(filename).suffix
        counter = 1
        while True:
            dest = file_dir / f"{_safe(stem)}_{counter}{suffix}"
            if not dest.exists():
                break
            counter += 1
    shutil.copy2(str(source_path), str(dest))
    return dest


def save_uploaded_file_bytes(username, judul_paper, data_bytes, filename):
    base = get_paper_base(username, judul_paper)
    file_dir = _ensure_dir(base / "file")
    safe_name = _safe(filename)
    filepath = file_dir / safe_name
    if filepath.exists():
        # BUG FIX: Same counter-loop fix as save_uploaded_file — re-sanitize each iteration
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        counter = 1
        while True:
            filepath = file_dir / f"{_safe(stem)}_{counter}{suffix}"
            if not filepath.exists():
                break
            counter += 1
    with open(filepath, "wb") as f:
        f.write(data_bytes)
    return filepath


def update_judul_paper(username, judul_paper, paper_data=None):
    """Save paper.json (legacy, title-based paths)."""
    base = get_paper_base(username, judul_paper)
    filepath = base / "paper.json"
    payload = {
        "judul": judul_paper,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if paper_data:
        payload["paper_data"] = paper_data
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    # Remove old judulpaper.json if exists
    old_path = base / "judulpaper.json"
    if old_path.exists():
        try:
            old_path.unlink()
        except Exception:
            pass
    return filepath


def update_judul_paper_by_id(paper_id, paper_title, journal_code, paper_data=None):
    """Save paper JSON to user/<paper_id>/<title>_<journal>.json.

    Removes old JSON files in that folder so only the latest title+journal
    combination is kept.
    """
    safe_id = _safe(paper_id, "unknown")
    paper_dir = _ensure_dir(USER_BASE / safe_id)
    safe_title = _safe(paper_title, "paper")[:60]
    safe_journal = _safe(journal_code, "journal")
    filename = f"{safe_title}_{safe_journal}.json"
    target = paper_dir / filename
    for old in paper_dir.glob("*.json"):
        if old.name.startswith("_tmp_"):
            continue
        if old != target:
            try:
                old.unlink()
            except Exception:
                pass
    payload = {
        "paper_id": paper_id,
        "title": paper_title,
        "journal": journal_code,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if paper_data:
        payload["paper_data"] = paper_data
    with open(target, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return target


def get_judul_paper(username, judul_paper):
    """Read paper.json with backward compat for old judulpaper.json."""
    base = get_paper_base(username, judul_paper)
    filepath = base / "paper.json"
    if not filepath.exists():
        # Backward compat: check old name
        old_path = base / "judulpaper.json"
        if old_path.exists():
            filepath = old_path
        else:
            return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def get_status_json_path(username, paper_id):
    """Get path to status.json for a paper."""
    base = get_paper_base_by_id(username, paper_id)
    return base / "status.json"


def _reconcile_status_json(status_data, paper_id):
    """Auto-heal status.json: fix filenames, add missing disk files.
    
    Handles:
    - Filenames with spaces (old code) → sanitize to match disk files
    - Files on disk missing from status.json → add them
    - Entries whose disk file doesn't exist → mark as missing
    """
    import re
    if not status_data or not isinstance(status_data, dict):
        return status_data
    
    files = status_data.get("files", [])
    if not files:
        return status_data
    
    # Derive paper dir from first file's path
    paper_dir = None
    for fe in files:
        p = fe.get("path", "")
        if p:
            paper_dir = Path(p).parent.parent
            break
    
    if not paper_dir or not paper_dir.exists():
        return status_data
    
    files_dir = paper_dir / "files"
    if not files_dir.exists():
        return status_data
    
    disk_files = {f.name for f in files_dir.iterdir() if f.suffix == ".txt"}
    if not disk_files:
        return status_data
    
    changed = False
    fixed_files = []
    seen_safe = set()
    
    for fe in files:
        fn = fe.get("filename", "")
        fp = fe.get("path", "")
        
        # Derive sanitized name from the filename
        txt_name = Path(fn).stem + ".txt"
        safe = re.sub(r'[^A-Za-z0-9._-]+', '_', txt_name).strip(" ._-") or "extracted"
        disk_path = files_dir / safe
        
        # If path is wrong or points to non-existent file, fix it
        if not fp or not Path(fp).exists():
            if disk_path.exists():
                fe["path"] = str(disk_path)
                if fe.get("filename") != safe:
                    fe["filename"] = safe
                changed = True
            else:
                # Try to find by original_name
                orig = fe.get("original_name", "")
                if orig:
                    txt = Path(orig).stem + ".txt"
                    safe_orig = re.sub(r'[^A-Za-z0-9._-]+', '_', txt).strip(" ._-") or "extracted"
                    alt_path = files_dir / safe_orig
                    if alt_path.exists():
                        fe["path"] = str(alt_path)
                        fe["filename"] = safe_orig
                        changed = True
        
        # Ensure filename matches sanitized version of path basename
        current_path = fe.get("path", "")
        if current_path:
            actual_name = Path(current_path).name
            if actual_name and actual_name != fe.get("filename"):
                fe["filename"] = actual_name
                changed = True
        
        # Deduplicate by sanitized filename
        safe_key = fe.get("filename", "")
        if safe_key not in seen_safe:
            seen_safe.add(safe_key)
            fixed_files.append(fe)
        else:
            changed = True
    
    # Add missing disk files not in status.json
    existing_safe = {fe.get("filename", "") for fe in fixed_files}
    for fname in sorted(disk_files):
        if fname not in existing_safe:
            txt_path = files_dir / fname
            fixed_files.append({
                "filename": fname,
                "path": str(txt_path),
                "original_name": fname.replace(".txt", ".pdf").replace("_", " "),
                "file_id": None,
                "uploaded_at": datetime.now(timezone.utc).isoformat()
            })
            changed = True
    
    if changed:
        status_data["files"] = fixed_files
        # Persist the fix
        try:
            paper_id_from_path = paper_dir.name if paper_dir else paper_id
            # Try to find username from path
            if paper_dir and "user" in paper_dir.parts:
                user_idx = paper_dir.parts.index("user") + 1
                if user_idx < len(paper_dir.parts):
                    username = paper_dir.parts[user_idx]
                    save_status_json(username, paper_id_from_path, status_data)
        except Exception:
            pass  # Non-critical: just return fixed data
    
    return status_data


def get_status_json(username, paper_id):
    """Read status.json for a paper. Returns empty structure if not exists.
    Also auto-heals filenames and missing files on read.
    """
    filepath = get_status_json_path(username, paper_id)
    if not filepath.exists():
        return {
            "paper_id": paper_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "facts": {},
            "files": [],
            "tables": [],
            "notes": []
        }
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            status = json.load(f)
        # Auto-heal on read
        return _reconcile_status_json(status, paper_id)
    except Exception as e:
        log.warning(f"Failed to read status.json for {paper_id}: {e}")
        return {
            "paper_id": paper_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "facts": {},
            "files": [],
            "tables": [],
            "notes": []
        }


def save_status_json(username, paper_id, status_data):
    """Save complete status.json for a paper (atomic write + file lock)."""
    import fcntl  # noqa: PLC0415
    filepath = get_status_json_path(username, paper_id)
    status_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    # Atomic write: write to unique .tmp then rename
    tmp_path = f"{filepath}.tmp.{uuid.uuid4()}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        json.dump(status_data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
        fcntl.flock(f, fcntl.LOCK_UN)
    os.replace(tmp_path, str(filepath))
    return filepath


def update_status_fact(username, paper_id, key, value, source="regex"):
    """Update a single fact in status.json."""
    status = get_status_json(username, paper_id)
    if "facts" not in status:
        status["facts"] = {}
    
    status["facts"][key] = {
        "value": value,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": source
    }
    
    return save_status_json(username, paper_id, status)


def add_status_file(username, paper_id, filename, filepath, metadata=None):
    """Add file entry to status.json (sanitizes filename for consistency)."""
    import re
    safe_name = re.sub(r'[^A-Za-z0-9._-]+', '_', str(filename or "")).strip(" ._-") or "untitled"
    status = get_status_json(username, paper_id)
    if "files" not in status:
        status["files"] = []
    
    file_entry = {
        "filename": safe_name,
        "path": str(filepath),
        "uploaded_at": datetime.now(timezone.utc).isoformat()
    }
    if metadata:
        file_entry["metadata"] = metadata
    
    # Remove duplicate if exists (match by filename or path)
    status["files"] = [f for f in status["files"]
                       if f["filename"] != safe_name and f.get("path") != str(filepath)]
    status["files"].append(file_entry)
    
    return save_status_json(username, paper_id, status)


def add_status_table(username, paper_id, table_name, source_file, rows=None, metadata=None):
    """Add table entry to status.json."""
    status = get_status_json(username, paper_id)
    if "tables" not in status:
        status["tables"] = []
    
    table_entry = {
        "name": table_name,
        "source_file": source_file,
        "added_at": datetime.now(timezone.utc).isoformat()
    }
    if rows is not None:
        table_entry["rows"] = rows
    if metadata:
        table_entry["metadata"] = metadata
    
    # Remove duplicate if exists
    status["tables"] = [t for t in status["tables"] if t["name"] != table_name]
    status["tables"].append(table_entry)
    
    return save_status_json(username, paper_id, status)


def add_status_note(username, paper_id, content):
    """Add a note to status.json."""
    status = get_status_json(username, paper_id)
    if "notes" not in status:
        status["notes"] = []
    
    note_entry = {
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    status["notes"].append(note_entry)
    
    return save_status_json(username, paper_id, status)


def save_paperfull_send_by_id(username, paper_id, data):
    """Save paperfull request to user/<username>/<paper_id>/paperfull/YYYYMMDD-HHMMSS-send.json"""
    base = get_paper_base_by_id(username, paper_id)
    pf_dir = _ensure_dir(base / "paperfull")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filepath = pf_dir / f"{ts}-send.json"
    payload = {"ts": datetime.now(timezone.utc).isoformat(), "direction": "send", **data}
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    log.debug("Saved paperfull send: %s", filepath)
    return filepath


def save_paperfull_recv_by_id(username, paper_id, data):
    """Save paperfull completion to user/<username>/<paper_id>/paperfull/YYYYMMDD-HHMMSS-recv.json"""
    base = get_paper_base_by_id(username, paper_id)
    pf_dir = _ensure_dir(base / "paperfull")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filepath = pf_dir / f"{ts}-recv.json"
    payload = {"ts": datetime.now(timezone.utc).isoformat(), "direction": "recv", **data}
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    log.debug("Saved paperfull recv: %s", filepath)
    return filepath


def build_status_context(username, paper_id, selected_facts=None, selected_files=None, selected_tables=None):
    """Build context string dari status.json untuk paperfull generation.
    
    Args:
        username: Username
        paper_id: Paper ID
        selected_facts: List of fact keys to include (None = all)
        selected_files: List of filenames to include (None = all)
        selected_tables: List of table names to include (None = all)
    
    Returns:
        Formatted string dengan facts, files, dan tables untuk inject ke prompt
    """
    status = get_status_json(username, paper_id)
    
    context_parts = []
    
    # Facts section
    facts = status.get("facts", {})
    if facts:
        if selected_facts is None:
            # Include all facts
            included_facts = facts
        else:
            # Filter by selection
            included_facts = {k: v for k, v in facts.items() if k in selected_facts}
        
        if included_facts:
            context_parts.append("## Paper Planning Facts\n")
            for key, fact_data in included_facts.items():
                value = fact_data.get("value", "")
                source = fact_data.get("source", "")
                context_parts.append(f"- **{key}**: {value} (source: {source})")
            context_parts.append("")
    
    # Files section
    files = status.get("files", [])
    if files:
        if selected_files is not None:
            # Flexible matching: try exact, sanitized, and path basename
            selected_set = set(selected_files)
            # Also add sanitized versions of selected filenames
            for sf in selected_files:
                txt_name = Path(sf).stem + ".txt"
                safe = re.sub(r'[^A-Za-z0-9._-]+', '_', txt_name).strip(" ._-") or "extracted"
                selected_set.add(safe)
            matched = []
            for f in files:
                fn = f.get("filename", "")
                # Derive sanitized name from original_name
                orig = f.get("original_name", "")
                txt_name = Path(orig).stem + ".txt"
                safe_from_orig = re.sub(r'[^A-Za-z0-9._-]+', '_', txt_name).strip(" ._-") or "extracted"
                # Get path basename
                p = f.get("path", "")
                path_basename = Path(p).name if p else ""
                
                if fn in selected_set or safe_from_orig in selected_set or path_basename in selected_set:
                    matched.append(f)
            included_files = matched
        else:
            included_files = files
        
        if included_files:
            context_parts.append("## Attached Files\n")
            for file_entry in included_files:
                filename = file_entry.get("filename", "unknown")
                filepath = file_entry.get("path", "")
                metadata = file_entry.get("metadata", {})
                
                context_parts.append(f"- **{filename}**")
                if metadata:
                    context_parts.append(f"  Metadata: {json.dumps(metadata, ensure_ascii=False)}")
                
                # Try to read file content if it's text-based
                if filepath:
                    try:
                        file_path = Path(filepath).resolve()
                        paper_base = get_paper_base_by_id(username, paper_id).resolve()
                        if not str(file_path).startswith(str(paper_base) + os.sep):
                            log.warning(f"build_status_context: path outside paper dir ignored: {filepath}")
                            continue
                        if file_path.exists() and file_path.suffix.lower() in ['.txt', '.md', '.csv', '.json']:
                            content = file_path.read_text(encoding='utf-8')
                            context_parts.append(f"  Content:\n```\n{content}\n```")
                    except Exception as e:
                        log.warning(f"Could not read file {filepath}: {e}")
            context_parts.append("")
    
    # Tables section
    tables = status.get("tables", [])
    if tables:
        if selected_tables is None:
            included_tables = tables
        else:
            included_tables = [t for t in tables if t.get("name") in selected_tables]
        
        if included_tables:
            context_parts.append("## Data Tables\n")
            for table_entry in included_tables:
                table_name = table_entry.get("name", "unknown")
                source_file = table_entry.get("source_file", "")
                rows = table_entry.get("rows")
                metadata = table_entry.get("metadata", {})
                
                context_parts.append(f"- **{table_name}**")
                context_parts.append(f"  Source: {source_file}")
                if rows is not None:
                    context_parts.append(f"  Rows: {rows}")
                if metadata:
                    context_parts.append(f"  Metadata: {json.dumps(metadata, ensure_ascii=False)}")
            context_parts.append("")
    
    # Notes section
    notes = status.get("notes", [])
    if notes:
        context_parts.append("## Additional Notes\n")
        for note in notes[-5:]:  # Only last 5 notes to avoid clutter
            content = note.get("content", "")
            timestamp = note.get("timestamp", "")
            context_parts.append(f"- {content} ({timestamp})")
        context_parts.append("")
    
    if not context_parts:
        return ""
    
    # Wrap in clear section markers
    result = "\n".join(context_parts)
    return f"\n\n## Context from Planning Session\n\n{result}\n"
