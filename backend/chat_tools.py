"""
Chat Tool Executor
==================
Executes tools requested by the AI during chat conversations.
"""

import os
import shlex
import json
import logging
import subprocess
import ipaddress
import socket
import threading
import time
import uuid
from urllib.parse import urlparse

import requests
from models import Paper, ProjectMemory, PaperFile, db


logger = logging.getLogger(__name__)


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
    logger.info(f"[EXECUTE_TOOL] Entering execute_tool: tool={tool_name}, user_id={user_id}, paper_id={paper_id}, args={json.dumps(arguments, ensure_ascii=False)[:300]}")
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
        elif tool_name == "RunSLR":
            return _run_slr_tool(
                paper_id, user_id,
                arguments.get("query", ""),
                arguments.get("sources"),
                int(arguments.get("top_k", 50) or 50),
                int(arguments.get("per_source", 60) or 60),
                arguments.get("year_from"),
                arguments.get("ai_model") or "V-OPUS",
            )
        elif tool_name == "GetLiterature":
            return _get_literature_tool(paper_id, user_id,
                                        int(arguments.get("limit", 50) or 50))
        elif tool_name == "ListAttachedFiles":
            return _list_attached_files(paper_id, user_id)
        elif tool_name == "ReadAttachedFile":
            return _read_attached_file(paper_id, user_id, arguments.get("file_id"))
        elif tool_name == "GetPaperContent":
            return _get_paper_content(paper_id, user_id)
        elif tool_name == "GetPaperSection":
            return _get_paper_section(paper_id, user_id, arguments.get("section", ""))
        elif tool_name == "GetPaperNumbering":
            return _get_paper_numbering(paper_id, user_id)
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


# Pretty labels for well-known memory keys we surface explicitly in the
# writer's custom_prompt. Anything not in this map is appended verbatim.
_MEMORY_KEY_LABELS = {
    "jurusan": "Jurusan",
    "topik": "Topik",
    "latar_belakang": "Latar belakang",
    "literatur_review_status": "Literatur review",
    "referensi_terpilih": "Referensi terpilih",
    "metode": "Metode",
    "data": "Data",
    "data_asli": "Data (asli)",
    "data_estimasi": "Data (estimasi)",
    "kesimpulan_target": "Kesimpulan target",
}
# Render order so the block is stable across calls.
_MEMORY_KEY_ORDER = [
    "jurusan",
    "topik",
    "latar_belakang",
    "literatur_review_status",
    "referensi_terpilih",
    "metode",
    "data",
    "data_asli",
    "data_estimasi",
    "kesimpulan_target",
]


def _format_literature_block(paper_id) -> str:
    """Render up to 30 LiteratureItem rows as a markdown block. Pinned +
    must_read first. Returns "" when empty."""
    if not paper_id:
        return ""
    try:
        from models import LiteratureItem
        items = (db.session.query(LiteratureItem)
                 .filter_by(paper_id=paper_id)
                 .order_by(LiteratureItem.pinned.desc(),
                           LiteratureItem.must_read.desc(),
                           LiteratureItem.score_total.desc(),
                           LiteratureItem.created_at.desc())
                 .limit(30).all())
    except Exception:
        return ""
    if not items:
        return ""
    lines = [
        "## Literature catalog (use these as the actual reference list — "
        "cite by title/DOI; do not invent references not in this list)",
    ]
    for i, it in enumerate(items, 1):
        authors_list = it.authors or []
        authors = ", ".join(authors_list[:3])
        if len(authors_list) > 3:
            authors += " et al."
        bits = [f"[L{i}] {it.title}"]
        if authors:
            bits.append(f"— {authors}")
        if it.year:
            bits.append(f"({it.year})")
        if it.venue:
            bits.append(f"in *{it.venue}*")
        if it.doi:
            bits.append(f"DOI: {it.doi}")
        elif it.url:
            bits.append(f"URL: {it.url}")
        line = " ".join(bits)
        if it.summary:
            line += f"\n   Summary: {it.summary[:240]}"
        lines.append(line)
    return "\n".join(lines)


def _format_memory_block(paper_id) -> str:
    """Render every ProjectMemory row for this paper as a single markdown
    block the writer leans on as source-of-truth. Returns "" when the paper
    has no memory yet. Never raises — DB issues fall back to empty."""
    if not paper_id:
        return ""
    try:
        mems = ProjectMemory.query.filter_by(paper_id=paper_id).all()
    except Exception:
        return ""
    if not mems:
        return ""

    by_key = {}
    for m in mems:
        k = (m.key or "").strip()
        if not k:
            continue
        by_key[k] = (m.value or "").strip()
    if not by_key:
        return ""

    lines = [
        "## Project facts (from chat memory — pakai SEMUA fakta ini sebagai source of truth)"
    ]
    seen = set()
    for k in _MEMORY_KEY_ORDER:
        if k in by_key:
            label = _MEMORY_KEY_LABELS.get(k, k)
            lines.append(f"- {label}: {by_key[k]}")
            seen.add(k)
    extras = sorted(k for k in by_key.keys() if k not in seen)
    for k in extras:
        label = _MEMORY_KEY_LABELS.get(k, k)
        lines.append(f"- {label}: {by_key[k]}")

    return "\n".join(lines)


def _run_slr_tool(paper_id, user_id, query, sources, top_k, per_source,
                   year_from, ai_model):
    """Enqueue an SLR job from the chat. Returns a structured proposal payload
    so the frontend can show a progress card and the chat blueprint can
    forward a friendly status to the model."""
    if not paper_id:
        return "Error: this chat is not linked to a paper."
    if not user_id:
        return "Error: not authenticated."
    q = (query or "").strip()
    if not q:
        return "Error: query is required (the literature topic)."

    try:
        from slr_worker import enqueue_slr_job
    except Exception as e:
        return f"Error: SLR worker unavailable ({e})"

    src_list = None
    if isinstance(sources, list) and sources:
        src_list = [s for s in sources if isinstance(s, str)]

    try:
        year_from_int = int(year_from) if year_from else None
    except (TypeError, ValueError):
        year_from_int = None

    if ai_model not in {"V-OPUS", "V-CLAUDE", "V-GPT", "V-GLM"}:
        ai_model = "V-OPUS"

    job_id = enqueue_slr_job(
        paper_id=paper_id, user_id=int(user_id), query=q,
        sources=src_list, per_source=max(10, min(int(per_source), 100)),
        top_k=max(10, min(int(top_k), 100)),
        year_from=year_from_int,
        ai_summarize=True, ai_model=ai_model,
    )

    payload = {
        "kind": "slr_job",
        "job_id": job_id,
        "query": q,
        "top_k": top_k,
        "ai_model": ai_model,
        "sources": src_list or "auto",
    }
    return PROPOSAL_PREFIX + json.dumps(payload, ensure_ascii=False)


def _get_literature_tool(paper_id, user_id, limit=50):
    """Return current LiteratureItem rows for the paper, ordered by relevance."""
    if not paper_id:
        return "No paper linked to this conversation."
    try:
        from models import LiteratureItem
    except Exception as e:
        return f"Error: cannot read literature ({e})"
    items = (db.session.query(LiteratureItem)
             .filter_by(paper_id=paper_id)
             .order_by(LiteratureItem.pinned.desc(),
                       LiteratureItem.score_total.desc(),
                       LiteratureItem.created_at.desc())
             .limit(max(1, min(int(limit), 100)))
             .all())
    if not items:
        return ("(Literature kosong. Pakai RunSLR untuk cari paper, atau import "
                "file PDF/DOCX dulu.)")
    rows = []
    for it in items:
        authors = ", ".join((it.authors or [])[:4])
        rows.append({
            "id": it.id,
            "title": it.title,
            "year": it.year,
            "authors": authors,
            "venue": it.venue,
            "doi": it.doi,
            "summary": (it.summary or it.abstract or "")[:400],
            "must_read": bool(it.must_read),
            "score": it.score_total,
        })
    return _truncate(json.dumps(rows, ensure_ascii=False, indent=2))


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

    # LITERATURE BLOCK — pull current LiteratureItem rows so the writer knows
    # which papers to cite. Pinned + must_read get prioritised.
    literature_block = _format_literature_block(paper_id)

    outline = _plan_outline(prompt, memory_lines, topic, style)

    # Build the writer's custom_prompt: full memory block as source-of-truth
    # FIRST (so every fact the user locked in survives the prompt.txt pipeline),
    # then the literature block (so the writer cites real papers from the
    # Literature tab), then the planner outline. All three are optional.
    parts = []
    mem_block = _format_memory_block(paper_id)
    if mem_block:
        parts.append(mem_block)
    if literature_block:
        parts.append(literature_block)
    if outline:
        parts.append(f"## Outline agreed with the user (follow it strictly)\n{outline}")
    custom_prompt = "\n\n".join(parts)

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
                "chunked": True,  # Use chunked generation to avoid 30s gateway timeouts
            },
            daemon=True,
        ).start()
        # Best-effort: tell the chat blueprint that this paper now has an
        # in-flight generation job so its /active-job endpoint can surface it.
        try:
            from chat import register_active_job
            register_active_job(paper_id, job_id)
        except Exception:
            pass  # registry not available — non-fatal
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
                "max_tokens": 32000,
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


# ─── Numbering helpers ────────────────────────────────────────────────────
# These mirror the frontend's `numbering` computed (paper.js): walk every
# section + subsection content list, assigning a sequential number to each
# `gambar` / `tabel` / `rumus` item in document order. We expose this to the
# AI so it can rewrite Fig./Table/Eq. mentions in section text after the user
# has reordered items.
_ROMAN_PAIRS = (
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
)


def _to_roman(num: int) -> str:
    out = ""
    for v, s in _ROMAN_PAIRS:
        while num >= v:
            out += s
            num -= v
    return out


def _walk_content_for_numbering(content_list, fig_idx, tbl_idx, eq_idx,
                                figs, tbls, eqs, section_title):
    """Walk a content list (already shape-normalized: list of dicts with id)
    and append entries to figs/tbls/eqs lists. Returns updated indices."""
    for item in (content_list or []):
        if not isinstance(item, dict):
            continue
        kind = item.get("id")
        if kind == "gambar":
            figs.append({
                "fig_number": fig_idx,
                "label": f"Fig. {fig_idx}",
                "title": item.get("Title") or "",
                "section": section_title,
                "has_path": bool(item.get("Path")),
                "prompt": (item.get("Prompt") or "")[:200],
            })
            fig_idx += 1
        elif kind == "tabel":
            tbls.append({
                "table_number": tbl_idx,
                "label": f"Table {_to_roman(tbl_idx)}",
                "title": item.get("Title") or "",
                "section": section_title,
            })
            tbl_idx += 1
        elif kind == "rumus":
            eqs.append({
                "eq_number": eq_idx,
                "label": f"Eq. ({eq_idx})",
                "section": section_title,
                "latex": (item.get("latex") or "")[:200],
            })
            eq_idx += 1
    return fig_idx, tbl_idx, eq_idx


def _get_paper_numbering(paper_id, user_id):
    """Return the current ordered numbering of figures/tables/equations.

    Use this BEFORE rewriting prose that mentions Fig./Table/Eq. — after the
    user reorders content boxes, the displayed numbers shift, so any prose
    that still says 'as shown in Fig. 2' may now refer to a different item.
    The AI should read this, then issue ProposeSection with corrected
    references in the section's text.
    """
    if not paper_id:
        return "No paper linked to this conversation."
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return "Paper not found."

    data = paper.data or {}
    figs, tbls, eqs = [], [], []
    fig_idx, tbl_idx, eq_idx = 1, 1, 1

    # Support both the array shape (sections=[...]) and the legacy
    # section1/section1a key shape used by some older papers.
    sections = data.get("sections")
    if isinstance(sections, list):
        for sec in sections:
            title = sec.get("title", "")
            fig_idx, tbl_idx, eq_idx = _walk_content_for_numbering(
                sec.get("content"), fig_idx, tbl_idx, eq_idx,
                figs, tbls, eqs, title)
            for sub in (sec.get("subsections") or []):
                fig_idx, tbl_idx, eq_idx = _walk_content_for_numbering(
                    sub.get("content"), fig_idx, tbl_idx, eq_idx,
                    figs, tbls, eqs, f"{title} — {sub.get('title','')}")
    else:
        skeys = sorted(
            (k for k in data.keys() if isinstance(k, str) and k.startswith("section") and k[7:].isdigit()),
            key=lambda k: int(k[7:]),
        )
        for sk in skeys:
            sec = data.get(sk) or {}
            if not isinstance(sec, dict):
                continue
            title = sec.get("title", "")
            fig_idx, tbl_idx, eq_idx = _walk_content_for_numbering(
                sec.get("content"), fig_idx, tbl_idx, eq_idx,
                figs, tbls, eqs, title)
            for subk in sorted(k for k in sec.keys() if isinstance(k, str) and k.startswith(sk) and k != sk):
                sub = sec.get(subk) or {}
                if not isinstance(sub, dict):
                    continue
                fig_idx, tbl_idx, eq_idx = _walk_content_for_numbering(
                    sub.get("content"), fig_idx, tbl_idx, eq_idx,
                    figs, tbls, eqs, f"{title} — {sub.get('title','')}")

    return _truncate(json.dumps(
        {"figures": figs, "tables": tbls, "equations": eqs},
        ensure_ascii=False, indent=2,
    ))


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
        "name": "RunSLR",
        "description": (
            "Kick off a full Systematic Literature Review search across multiple academic "
            "indexes (OpenAlex, Crossref, Semantic Scholar, arXiv, DBLP, Europe PMC, IEEE, "
            "SINTA/Garuda). The job is queued (max 10 workers) and runs asynchronously: "
            "fetch all sources in parallel, dedup by DOI/title, rank with SBERT + citation "
            "+ recency + venue quality, then summarize the top 50 with V-OPUS. Results are "
            "automatically saved as LiteratureItem rows that show up in the user's Literature "
            "tab. Use this when the user asks for a literature review, related work, or "
            "to populate references."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query / topic."},
                "sources": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional: restrict to specific sources (e.g. ['ieee','sinta']).",
                },
                "top_k": {"type": "integer", "description": "How many to summarize (default 50, max 100)."},
                "per_source": {"type": "integer", "description": "Max results per source (default 60)."},
                "year_from": {"type": "integer", "description": "Optional cutoff year."},
                "ai_model": {"type": "string", "description": "V-OPUS|V-CLAUDE|V-GPT|V-GLM. Default V-OPUS."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "GetLiterature",
        "description": (
            "Read the current Literature tab rows for this paper. Returns title, authors, "
            "year, venue, DOI, AI summary, must_read flag, score. Use this to give the user "
            "a tabel rangkuman literatur, or to confirm what references will be cited before "
            "GenerateFullPaper."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Default 50, max 100."},
            },
            "required": [],
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
        "name": "GetPaperNumbering",
        "description": (
            "Return the current ORDERED list of figures, tables, and equations "
            "in this paper, with their actual displayed numbers (Fig. 1, "
            "Table II, Eq. (3), …) and their parent section. Numbers are "
            "computed live from item order, so after a reorder the displayed "
            "numbers will not match what older prose says. Call this BEFORE "
            "rewriting any section that mentions Fig./Table/Eq. references — "
            "then use ProposeSection to push back corrected text. Used by the "
            "user's 'rapikan' command."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
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
