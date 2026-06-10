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

import json
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

# Base directory
BACKEND_DIR = Path(__file__).parent.parent.parent
USER_BASE = BACKEND_DIR / "user"

_SAFE_RE = re.compile(r'[^A-Za-z0-9._-]+')

def _safe(name, fallback="unknown"):
    s = _SAFE_RE.sub("_", str(name or "")).strip("._-")
    return s or fallback


def get_username(user_id=None, email=None):
    if email:
        return _safe(email.split("@")[0])
    if user_id:
        try:
            from database.models import User
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
    """Return base dir for paper_id-based storage: user/<username>/<paper_id>/"""
    safe_user = _safe(username)
    safe_id = _safe(paper_id, "unknown")
    return _ensure_dir(USER_BASE / safe_user / safe_id)

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
        "paper_data": paper_data,
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
        "paper_data": paper_data,
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
    """Save extracted text content as .txt file in file/ directory."""
    base = get_paper_base(username, judul_paper)
    file_dir = _ensure_dir(base / "file")
    txt_name = Path(filename).stem + ".txt"
    safe_name = _safe(txt_name)
    filepath = file_dir / safe_name
    if filepath.exists():
        stem = filepath.stem
        counter = 1
        while filepath.exists():
            filepath = file_dir / f"{stem}_{counter}.txt"
            counter += 1
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(text_content)
    return filepath


def save_uploaded_file(username, judul_paper, source_path, filename):
    base = get_paper_base(username, judul_paper)
    file_dir = _ensure_dir(base / "file")
    safe_name = _safe(filename)
    dest = file_dir / safe_name
    if dest.exists():
        stem = dest.stem
        suffix = dest.suffix
        counter = 1
        while dest.exists():
            dest = file_dir / f"{stem}_{counter}{suffix}"
            counter += 1
    shutil.copy2(str(source_path), str(dest))
    return dest


def save_uploaded_file_bytes(username, judul_paper, data_bytes, filename):
    base = get_paper_base(username, judul_paper)
    file_dir = _ensure_dir(base / "file")
    safe_name = _safe(filename)
    filepath = file_dir / safe_name
    if filepath.exists():
        stem = filepath.stem
        suffix = filepath.suffix
        counter = 1
        while filepath.exists():
            filepath = file_dir / f"{stem}_{counter}{suffix}"
            counter += 1
    with open(filepath, "wb") as f:
        f.write(data_bytes)
    return filepath


def update_judul_paper(username, judul_paper, paper_data=None):
    """Save paper.json (renamed from judulpaper.json for clarity)."""
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


def get_status_json(username, paper_id):
    """Read status.json for a paper. Returns empty structure if not exists."""
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
            return json.load(f)
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
    """Save complete status.json for a paper."""
    filepath = get_status_json_path(username, paper_id)
    status_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(status_data, f, ensure_ascii=False, indent=2)
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
    """Add file entry to status.json."""
    status = get_status_json(username, paper_id)
    if "files" not in status:
        status["files"] = []
    
    file_entry = {
        "filename": filename,
        "path": str(filepath),
        "uploaded_at": datetime.now(timezone.utc).isoformat()
    }
    if metadata:
        file_entry["metadata"] = metadata
    
    # Remove duplicate if exists
    status["files"] = [f for f in status["files"] if f["filename"] != filename]
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
        if selected_files is None:
            included_files = files
        else:
            included_files = [f for f in files if f.get("filename") in selected_files]
        
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
                        file_path = Path(filepath)
                        if file_path.exists() and file_path.suffix.lower() in ['.txt', '.md', '.csv', '.json']:
                            content = file_path.read_text(encoding='utf-8')
                            # Limit content to avoid huge prompts
                            if len(content) > 2000:
                                content = content[:2000] + "\n... (truncated)"
                            context_parts.append(f"  Content preview:\n```\n{content}\n```")
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
