"""
Chat Tool Executor
==================
Executes tools requested by the AI during chat conversations.
"""

import os
import shlex
import json
import subprocess
import ipaddress
import socket
import threading
import time
import uuid
from urllib.parse import urlparse

import requests
from models import Paper, ProjectMemory, PaperFile, db


SAFE_BASH_COMMANDS = {'grep', 'find', 'wc', 'cat', 'head', 'tail', 'ls', 'echo', 'date', 'pwd'}

MAX_RESULT_LENGTH = 6000

# Files / paths the AI must NEVER be able to read.
SENSITIVE_FILE_NAMES = {
    '.env', '.env.local', '.env.production', '.env.development',
    'mydatabase.db', 'requirements.txt.lock', 'id_rsa', 'id_dsa',
    'id_ecdsa', 'id_ed25519', '.gitconfig',
}
SENSITIVE_PATH_FRAGMENTS = (
    '/.git/', '/node_modules/', '/uploads/', '/exports/',
    '/.ssh/', '/certs/', '/__pycache__/',
)
ALLOWED_READ_ROOTS = (
    '/home/sirobo/papergenerator/backend/prompt/',
    '/home/sirobo/papergenerator/backend/template/',
    '/home/sirobo/papergenerator/frontend/src/',
)


def execute_tool(tool_name, arguments, user_id, paper_id=None):
    try:
        if tool_name == "WebSearch":
            return _web_search(arguments.get("query", ""))
        elif tool_name == "WebFetch":
            return _web_fetch(arguments.get("url", ""), arguments.get("prompt", ""))
        elif tool_name == "SearchPapers":
            return _search_papers(
                arguments.get("query", ""),
                int(arguments.get("limit_per_source", 3) or 3),
                arguments.get("sources"),
            )
        elif tool_name == "GenerateFullPaper":
            return _generate_full_paper(
                paper_id, user_id,
                arguments.get("prompt", ""),
                arguments.get("topic"),
                arguments.get("style"),
                arguments.get("use_attached_files", True),
            )
        elif tool_name == "ListAttachedFiles":
            return _list_attached_files(paper_id, user_id)
        elif tool_name == "ReadAttachedFile":
            return _read_attached_file(paper_id, user_id, arguments.get("file_id"))
        elif tool_name == "GetPaperContent":
            return _get_paper_content(paper_id, user_id)
        elif tool_name == "GetPaperSection":
            return _get_paper_section(paper_id, user_id, arguments.get("section", ""))
        elif tool_name == "Read":
            return _safe_read(arguments.get("file_path", ""))
        elif tool_name == "Bash":
            return _safe_bash(arguments.get("command", ""))
        elif tool_name == "SaveMemory":
            return _save_memory(
                paper_id, user_id,
                arguments.get("key", ""),
                arguments.get("value", ""),
                arguments.get("kind", "fact"),
            )
        elif tool_name == "GetMemory":
            return _get_memory(paper_id, user_id, arguments.get("key"))
        elif tool_name == "ListMemory":
            return _list_memory(paper_id, user_id)
        elif tool_name == "DeleteMemory":
            return _delete_memory(paper_id, user_id, arguments.get("key", ""))
        # ─── Paper-edit proposal tools ──────────────────────────────────────
        # These tools don't mutate the paper. They emit a proposal payload that
        # the frontend collects and shows to the user for accept/reject.
        elif tool_name == "ProposeTitle":
            return _propose("title", {"value": arguments.get("title", "")})
        elif tool_name == "ProposeAbstract":
            return _propose("abstract", {"value": arguments.get("abstract", "")})
        elif tool_name == "ProposeKeywords":
            return _propose("keywords", {"value": arguments.get("keywords") or []})
        elif tool_name == "ProposeSection":
            return _propose("section", {
                "section_index": arguments.get("section_index"),
                "title": arguments.get("title"),
                "content": arguments.get("content"),
            })
        elif tool_name == "ProposeReference":
            return _propose("reference", {
                "ref_index": arguments.get("ref_index"),
                "value": arguments.get("value", ""),
            })
        elif tool_name == "ProposeJournal":
            return _propose("journal", {"value": arguments.get("journal", "")})
        elif tool_name == "RequestExportDocx":
            return _propose("export_docx", {})
        elif tool_name in ("Write", "Edit"):
            return "Tool not permitted in chat environment for security reasons."
        else:
            return f"Unknown tool: {tool_name}"
    except Exception as e:
        return f"Tool execution error: {str(e)}"


# Sentinel prefix that the frontend uses to detect a structured proposal
# payload coming back from a tool call.
PROPOSAL_PREFIX = "<<PROPOSAL>>"


def _propose(kind: str, fields: dict) -> str:
    """Wrap a proposal as a JSON payload prefixed with PROPOSAL_PREFIX."""
    payload = {"kind": kind, **fields}
    return PROPOSAL_PREFIX + json.dumps(payload, ensure_ascii=False)


def _truncate(text, max_len=MAX_RESULT_LENGTH):
    if not isinstance(text, str):
        text = str(text)
    if len(text) <= max_len:
        return text
    # Encode to bytes, slice, then decode while ignoring partial multibyte
    # tails. Otherwise we sometimes hand the upstream API an invalid UTF-8
    # sequence which surfaces as a 500. Slow path is fine here — short results
    # never enter this branch.
    head = text[:max_len].encode('utf-8', errors='ignore')[:max_len]
    head = head.decode('utf-8', errors='ignore')
    return head + f"\n\n... [truncated, {len(text)} chars total]"


def _web_search(query):
    if not query:
        return "Error: query is required"
    try:
        resp = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"},
            timeout=10
        )
        from html.parser import HTMLParser

        class DDGParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.results = []
                self.in_result = False
                self.current = ""

            def handle_starttag(self, tag, attrs):
                attrs_dict = dict(attrs)
                if tag == "a" and "result__a" in attrs_dict.get("class", ""):
                    self.in_result = True
                    self.current = ""

            def handle_endtag(self, tag):
                if tag == "a" and self.in_result:
                    self.in_result = False
                    if self.current.strip():
                        self.results.append(self.current.strip())

            def handle_data(self, data):
                if self.in_result:
                    self.current += data

        parser = DDGParser()
        parser.feed(resp.text)
        if parser.results:
            return _truncate("\n".join(f"- {r}" for r in parser.results[:10]))
        return "No results found."
    except Exception as e:
        return f"Search error: {str(e)}"


def _web_fetch(url, prompt):
    if not url:
        return "Error: url is required"
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return "Error: only http/https URLs are allowed."
        host = parsed.hostname or ''
        if not host:
            return "Error: invalid URL host."
        # Block SSRF to private / loopback / link-local ranges.
        try:
            for info in socket.getaddrinfo(host, None):
                ip = ipaddress.ip_address(info[4][0])
                if (ip.is_private or ip.is_loopback or ip.is_link_local
                        or ip.is_multicast or ip.is_reserved):
                    return "Error: requests to internal addresses are not allowed."
        except (socket.gaierror, ValueError):
            return "Error: could not resolve URL."

        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"},
            timeout=15,
            allow_redirects=False,
        )
        text = resp.text[:MAX_RESULT_LENGTH]
        import re
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return _truncate(text)
    except Exception as e:
        return f"Fetch error: {str(e)}"


def _search_papers(query, limit_per_source=3, sources=None):
    """SLR helper. Calls searchPaper.search_all and FILTERS:
       - drops entries with errors
       - drops entries with no usable URL/DOI/pdf_url
       - drops entries without a title
    Only valid, accessible papers reach the model."""
    if not query:
        return "Error: query is required"
    try:
        # Local import keeps the module light if backend boots without internet
        from searchPaper import search_all
    except Exception as e:
        return f"SearchPapers unavailable: {e}"

    src_list = None
    if isinstance(sources, list) and sources:
        src_list = [s for s in sources if isinstance(s, str)]

    try:
        raw = search_all(query, limit_per_source=max(1, min(int(limit_per_source), 5)),
                         sources=src_list, include_keyed=False)
    except Exception as e:
        return f"SearchPapers error: {e}"

    cleaned = []
    seen = set()
    for r in raw:
        if not isinstance(r, dict) or "error" in r:
            continue
        title = (r.get("title") or "").strip()
        if not title:
            continue
        url = (r.get("url") or "").strip()
        pdf = (r.get("pdf_url") or "").strip()
        doi = (r.get("doi") or "").strip()
        # Must have at least one accessible identifier
        if not (url or pdf or doi):
            continue
        # Dedupe by DOI / URL / lowered title
        key = doi or url or pdf or title.lower()
        if key in seen:
            continue
        seen.add(key)

        cleaned.append({
            "source": r.get("source"),
            "title": title,
            "authors": (r.get("authors") or [])[:6],
            "year": r.get("year"),
            "doi": doi,
            "url": url or (f"https://doi.org/{doi}" if doi else ""),
            "pdf_url": pdf,
            "abstract": (r.get("abstract") or "")[:600],
        })

    if not cleaned:
        return "(No valid, accessible papers found. Try a more specific query or different keywords.)"

    # Cap output volume so the model context stays bounded
    cleaned = cleaned[:25]
    payload = {"query": query, "count": len(cleaned), "results": cleaned}
    return _truncate(json.dumps(payload, ensure_ascii=False, indent=2))


def _list_attached_files(paper_id, user_id):
    if not paper_id:
        return "No paper linked to this conversation."
    files = (PaperFile.query
             .filter_by(paper_id=paper_id, user_id=user_id)
             .order_by(PaperFile.created_at.desc())
             .all())
    if not files:
        return "(no files attached to this paper)"
    lines = []
    for f in files:
        size_kb = round((f.size_bytes or 0) / 1024)
        preview_chars = len(f.extracted_text or "")
        lines.append(
            f"- id={f.id} name='{f.original_name}' ext={f.ext} "
            f"size={size_kb}KB extracted_chars={preview_chars}"
        )
    return _truncate("\n".join(lines))


def _read_attached_file(paper_id, user_id, file_id):
    if not paper_id:
        return "No paper linked to this conversation."
    if file_id is None:
        return "Error: file_id is required (use ListAttachedFiles first)."
    try:
        fid = int(file_id)
    except (TypeError, ValueError):
        return "Error: file_id must be an integer."
    f = PaperFile.query.filter_by(id=fid, paper_id=paper_id, user_id=user_id).first()
    if not f:
        return f"File id={fid} not found in this paper."
    text = f.extracted_text or ""
    if not text:
        return f"(file '{f.original_name}' has no extracted text)"
    return _truncate(f"# {f.original_name} ({f.ext})\n\n{text}")


def _generate_full_paper(paper_id, user_id, prompt, topic=None, style=None, use_attached_files=True):
    """Kick off the same /api/generate-full job pipeline used by the dashboard,
    but from a chat tool call. Auto-injects extracted text from any files the
    user has attached to this paper. Also runs a quick planner pass first so
    the writer agent gets a concrete outline + scope (multi-stage cooperation
    on a single model)."""
    if not user_id:
        return "Error: not authenticated."
    prompt = (prompt or "").strip()
    if not prompt:
        return "Error: prompt is required (the paper title or topic)."

    api_key = os.getenv("AIOTOMASI_APIKEY")
    if not api_key:
        return "Error: AIOTOMASI_APIKEY is not configured on the server."

    # Collect attached file texts (capped) so the generator can use them as refs
    pdf_texts = []
    if use_attached_files and paper_id:
        files = (PaperFile.query
                 .filter_by(paper_id=paper_id, user_id=user_id)
                 .order_by(PaperFile.created_at.desc())
                 .limit(5).all())
        for f in files:
            if f.extracted_text:
                pdf_texts.append(f"# {f.original_name}\n{f.extracted_text}")

    # PLANNER PASS — turn the chat history into a concrete outline before the
    # writer takes over. We snapshot project memory so the planner sees what
    # the user already locked in (target journal, methodology, etc.).
    memory_lines = ""
    if paper_id:
        try:
            mems = ProjectMemory.query.filter_by(paper_id=paper_id).all()
            if mems:
                memory_lines = "\n".join(f"- {m.key}: {m.value}" for m in mems[:25])
        except Exception:
            memory_lines = ""

    outline = _plan_outline(prompt, memory_lines, topic, style)
    custom_prompt = ""
    if outline:
        custom_prompt = (
            "## Outline agreed with the user (follow it strictly)\n"
            f"{outline}\n"
        )

    # Run inside the existing app context so Flask's job machinery is available
    try:
        from app import app, _job_create, _run_generate_full_job
    except Exception as e:
        return f"Error: cannot import app job runner ({e})"

    job_id = uuid.uuid4().hex[:12]
    try:
        with app.app_context():
            _job_create(job_id, int(user_id), prompt)
        threading.Thread(
            target=_run_generate_full_job,
            args=(job_id, prompt, int(user_id)),
            kwargs={
                "topic": topic,
                "style": style,
                "pdf_texts": pdf_texts,
                "custom_prompt": custom_prompt,
                "paper_id": paper_id,
            },
            daemon=True,
        ).start()
    except Exception as e:
        return f"Error starting job: {e}"

    # Return a structured payload so the frontend can show the job spinner
    payload = {
        "kind": "generate_full",
        "job_id": job_id,
        "prompt": prompt,
        "topic": topic,
        "style": style,
        "attached_files_used": len(pdf_texts),
        "outlined": bool(outline),
    }
    return PROPOSAL_PREFIX + json.dumps(payload, ensure_ascii=False)


def _plan_outline(prompt: str, memory_lines: str, topic: str, style: str) -> str:
    """Lightweight planner agent. One synchronous call to the same upstream
    model with a planner system prompt. Returns plain-text outline. Failures
    are non-fatal — the writer step is still ok with an empty custom_prompt."""
    base = (os.getenv("AIOTOMASI_API") or "").rstrip("/")
    api_key = os.getenv("AIOTOMASI_APIKEY") or ""
    model = os.getenv("AIOTOMASI_MODEL") or ""
    if not (base and api_key and model):
        return ""

    sys_prompt = (
        "You are an academic-paper PLANNER agent. Given a topic and any "
        "memory snapshot from prior chat, produce a concrete writing plan "
        "for a publication-ready paper. Output PLAIN TEXT, ~250-400 words, "
        "no JSON, no markdown headers. Cover:\n"
        "- 1 specific paper title (descriptive, not generic)\n"
        "- The exact problem statement and contribution\n"
        "- Methodology in detail (algorithms, parameters, datasets/hardware)\n"
        "- Experimental setup with concrete numbers (e.g., 3 AGVs, 20x20 grid)\n"
        "- 4-6 expected result figures/tables with the metrics they will report\n"
        "- 8-12 reference candidates by topic area (no fake DOIs)\n"
        "- Section list and one-line summary per section\n"
        "Be specific. The writer agent will follow this plan literally."
    )

    user_prompt = f"Paper topic / title: {prompt}\n"
    if memory_lines:
        user_prompt += f"\n## Project memory\n{memory_lines}\n"
    if topic:
        user_prompt += f"\n## Topic guide: {topic}"
    if style:
        user_prompt += f"\n## Citation style: {style}"

    try:
        resp = requests.post(
            base + "/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "max_tokens": 2000,
            },
            timeout=90,
        )
        if resp.status_code != 200:
            return ""
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            return ""
        content = choices[0].get("message", {}).get("content") or ""
        return content.strip()[:6000]
    except Exception:
        return ""


def _get_paper_content(paper_id, user_id):
    if not paper_id:
        return "No paper linked to this conversation."
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return "Paper not found."
    return _truncate(json.dumps(paper.data, ensure_ascii=False, indent=2))


def _get_paper_section(paper_id, user_id, section):
    if not paper_id:
        return "No paper linked to this conversation."
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return "Paper not found."
    data = paper.data or {}
    if section in data:
        content = data[section]
        if isinstance(content, (dict, list)):
            return _truncate(json.dumps(content, ensure_ascii=False, indent=2))
        return _truncate(str(content))
    sections = data.get("sections", [])
    for s in sections:
        if s.get("title", "").lower() == section.lower():
            return _truncate(json.dumps(s, ensure_ascii=False, indent=2))
    return f"Section '{section}' not found. Available keys: {list(data.keys())}"


def _safe_read(file_path):
    if not file_path:
        return "Error: file_path is required"
    abs_path = os.path.abspath(file_path)
    real_path = os.path.realpath(abs_path)  # resolve symlinks
    # Must be inside one of the allow-listed roots (subset of project dir)
    if not any(real_path.startswith(p) for p in ALLOWED_READ_ROOTS):
        return "Access denied: path is outside the allowed read roots."
    name = os.path.basename(real_path).lower()
    if name in SENSITIVE_FILE_NAMES:
        return "Access denied: this file is restricted."
    if any(frag in real_path for frag in SENSITIVE_PATH_FRAGMENTS):
        return "Access denied: path contains a restricted fragment."
    if not os.path.isfile(real_path):
        return f"File not found: {file_path}"
    try:
        # Refuse anything bigger than 256KB to keep prompts bounded
        if os.path.getsize(real_path) > 256 * 1024:
            return "Error: file too large to read (>256KB)."
        with open(real_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        return _truncate(content)
    except Exception as e:
        return f"Read error: {str(e)}"


def _safe_bash(command):
    if not command:
        return "Error: command is required"
    # Reject anything that looks like shell metacharacters BEFORE parsing.
    forbidden = (';', '&&', '||', '|', '`', '$(', '$\\', '>', '<', '\n', '\r')
    if any(tok in command for tok in forbidden):
        return "Error: shell metacharacters are not allowed."
    try:
        argv = shlex.split(command)
    except ValueError as e:
        return f"Error: could not parse command ({e})."
    if not argv:
        return "Error: empty command."
    base_cmd = os.path.basename(argv[0])
    if base_cmd not in SAFE_BASH_COMMANDS:
        return f"Command '{base_cmd}' not allowed. Allowed: {', '.join(sorted(SAFE_BASH_COMMANDS))}"
    # Reject path arguments that escape the project or hit sensitive files.
    for arg in argv[1:]:
        low = arg.lower()
        if any(frag in arg for frag in SENSITIVE_PATH_FRAGMENTS):
            return "Error: argument references a restricted path."
        if any(low.endswith('/' + s) or low == s for s in SENSITIVE_FILE_NAMES):
            return "Error: argument references a restricted file."
        if arg.startswith('/') and not arg.startswith('/home/sirobo/papergenerator/'):
            return "Error: only paths inside the project are allowed."
    try:
        result = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            timeout=10,
            cwd='/home/sirobo/papergenerator',
        )
        output = result.stdout
        if result.stderr:
            output += f"\nSTDERR: {result.stderr}"
        return _truncate(output) if output.strip() else "(no output)"
    except subprocess.TimeoutExpired:
        return "Command timed out (10s limit)."
    except FileNotFoundError:
        return f"Command '{base_cmd}' not found."
    except Exception as e:
        return f"Bash error: {str(e)}"


def _normalize_key(key: str) -> str:
    k = (key or "").strip().lower().replace(" ", "_")
    return k[:120]


def _save_memory(paper_id, user_id, key, value, kind="fact"):
    if not paper_id:
        return "Error: this chat is not linked to a paper. Memory cannot be saved."
    key = _normalize_key(key)
    value = (value or "").strip()
    if not key:
        return "Error: 'key' is required (e.g. 'tentative_title', 'methodology', 'tone')."
    if not value:
        return "Error: 'value' is required."

    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return "Paper not found."

    entry = ProjectMemory.query.filter_by(paper_id=paper_id, key=key).first()
    if entry:
        entry.value = value
        entry.kind = kind or entry.kind or "fact"
    else:
        entry = ProjectMemory(
            paper_id=paper_id,
            user_id=user_id,
            key=key,
            value=value,
            kind=kind or "fact",
        )
        db.session.add(entry)
    db.session.commit()
    return f"Saved memory '{key}' (kind={entry.kind}). It will be available in all chats of this paper."


def _get_memory(paper_id, user_id, key):
    if not paper_id:
        return "No paper linked to this conversation."
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return "Paper not found."
    if key:
        entry = ProjectMemory.query.filter_by(paper_id=paper_id, key=_normalize_key(key)).first()
        if not entry:
            return f"No memory found for key '{key}'."
        return f"{entry.key} ({entry.kind}): {entry.value}"
    return _list_memory(paper_id, user_id)


def _list_memory(paper_id, user_id):
    if not paper_id:
        return "No paper linked to this conversation."
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return "Paper not found."
    entries = ProjectMemory.query.filter_by(paper_id=paper_id).order_by(ProjectMemory.updated_at.desc()).all()
    if not entries:
        return "(memory is empty for this paper)"
    lines = [f"- [{e.kind}] {e.key}: {e.value}" for e in entries]
    return _truncate("\n".join(lines))


def _delete_memory(paper_id, user_id, key):
    if not paper_id:
        return "No paper linked to this conversation."
    if not key:
        return "Error: 'key' is required."
    entry = ProjectMemory.query.filter_by(paper_id=paper_id, key=_normalize_key(key)).first()
    if not entry:
        return f"No memory found for key '{key}'."
    db.session.delete(entry)
    db.session.commit()
    return f"Deleted memory '{key}'."


def get_memory_summary(paper_id) -> str:
    """Used by chat.py to inject saved memory into the system prompt."""
    if not paper_id:
        return ""
    entries = ProjectMemory.query.filter_by(paper_id=paper_id).order_by(ProjectMemory.updated_at.desc()).all()
    if not entries:
        return ""
    lines = [f"- [{e.kind}] {e.key}: {e.value}" for e in entries]
    return "\n".join(lines)


CHAT_TOOLS = [
    {
        "name": "WebSearch",
        "description": "Search the web (DuckDuckGo).",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "WebFetch",
        "description": "Fetch and extract text from a URL.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "prompt": {"type": "string"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "SearchPapers",
        "description": (
            "Multi-source academic search (OpenAlex, Crossref, arXiv, Semantic Scholar, "
            "Europe PMC, PubMed, DOAJ, DBLP, HAL, PLOS, Zenodo, …). Use this for SLR-style "
            "literature search. Results are pre-filtered: entries without a usable URL/DOI/PDF "
            "are dropped. Each result has source, title, authors, year, doi, url, pdf_url, abstract."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit_per_source": {"type": "integer"},
                "sources": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional: restrict to specific sources (e.g. ['arxiv','openalex']).",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "GenerateFullPaper",
        "description": (
            "Generate a COMPLETE paper (Sections I–V + references) using the AI pipeline. "
            "Only call this AFTER you've discussed the topic with the user and gathered "
            "enough detail (problem, methodology, dataset/case, target venue). Auto-uses any "
            "files the user attached as references (no manual step needed). Returns a job_id; "
            "the frontend will poll and load the result into the editor."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Full topic / proposed title."},
                "topic": {"type": "string", "description": "Optional topic slug from /api/topics."},
                "style": {"type": "string", "description": "Optional citation-style slug from /api/styles."},
                "use_attached_files": {"type": "boolean", "description": "Default true."},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "ListAttachedFiles",
        "description": "List files (PDF/DOCX/TXT/MD) the user uploaded to THIS paper. Returns id, name, size, extracted_chars.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "ReadAttachedFile",
        "description": "Read the extracted text of one attached file by id (use ListAttachedFiles to find the id).",
        "input_schema": {
            "type": "object",
            "properties": {"file_id": {"type": "integer"}},
            "required": ["file_id"],
        },
    },
    {
        "name": "GetPaperContent",
        "description": "Get the full JSON of the current paper.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "GetPaperSection",
        "description": "Get one section by name.",
        "input_schema": {
            "type": "object",
            "properties": {"section": {"type": "string"}},
            "required": ["section"],
        },
    },
    {
        "name": "Read",
        "description": "Read a file in the project.",
        "input_schema": {
            "type": "object",
            "properties": {"file_path": {"type": "string"}},
            "required": ["file_path"],
        },
    },
    {
        "name": "Bash",
        "description": "Read-only bash (grep/find/wc/cat/head/tail/ls/echo/date/pwd).",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
    {
        "name": "SaveMemory",
        "description": "Save a durable fact about THIS paper. Shared across all chats. Keys are short snake_case (e.g. tentative_title).",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "value": {"type": "string"},
                "kind": {"type": "string"},
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "GetMemory",
        "description": "Read one memory by key (or list all if omitted).",
        "input_schema": {
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": [],
        },
    },
    {
        "name": "ListMemory",
        "description": "List all memory entries.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "DeleteMemory",
        "description": "Delete a memory entry by key.",
        "input_schema": {
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
        },
    },
    {
        "name": "ProposeTitle",
        "description": "Propose a new title (pending diff).",
        "input_schema": {
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
        },
    },
    {
        "name": "ProposeAbstract",
        "description": "Propose a new abstract (pending diff).",
        "input_schema": {
            "type": "object",
            "properties": {"abstract": {"type": "string"}},
            "required": ["abstract"],
        },
    },
    {
        "name": "ProposeKeywords",
        "description": "Propose a new keyword list (pending diff, replaces all).",
        "input_schema": {
            "type": "object",
            "properties": {
                "keywords": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["keywords"],
        },
    },
    {
        "name": "ProposeSection",
        "description": "Propose section change. section_index null = append new.",
        "input_schema": {
            "type": "object",
            "properties": {
                "section_index": {"type": ["integer", "null"]},
                "title": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "ProposeReference",
        "description": "Propose reference change. ref_index null = append.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ref_index": {"type": ["integer", "null"]},
                "value": {"type": "string"},
            },
            "required": ["value"],
        },
    },
    {
        "name": "ProposeJournal",
        "description": "Switch journal/template (auto-applied, no diff).",
        "input_schema": {
            "type": "object",
            "properties": {"journal": {"type": "string"}},
            "required": ["journal"],
        },
    },
    {
        "name": "RequestExportDocx",
        "description": "Trigger DOCX export of current paper (auto-applied).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]
