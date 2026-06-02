"""
Chat Tool Executor
==================
Executes tools requested by the AI during chat conversations.
"""

import datetime
import ipaddress
import json
import logging
import os
import shlex
import socket
import subprocess
import threading
import uuid
from urllib.parse import urlparse

import requests

from database.models import Paper, PaperFile, PaperImage, ProjectMemory, db

logger = logging.getLogger(__name__)


def _check_paper_lock(paper_id: str, operation_type: str) -> tuple[bool, str | None]:
    """Check if paper is locked by another operation.

    Args:
        paper_id: Paper ID to check
        operation_type: 'generate' | 'edit_apply' | 'slr' | 'chat'

    Returns:
        (allowed, reason): (True, None) if allowed, (False, reason) if blocked
    """
    paper = Paper.query.get(paper_id)
    if not paper or not paper.active_operation:
        return True, None

    if paper.active_operation == "generating":
        if operation_type in ["generate", "edit_apply"]:
            return False, "Paper sedang di-generate. Tunggu selesai atau cancel dulu."

    return True, None


def _set_paper_lock(paper_id: str, operation: str, job_id: str = None):
    """Set paper lock."""
    from datetime import datetime

    paper = Paper.query.get(paper_id)
    paper.active_operation = operation
    paper.active_operation_job_id = job_id
    paper.active_operation_started_at = datetime.utcnow()
    db.session.commit()


def _clear_paper_lock(paper_id: str):
    """Clear paper lock."""
    paper = Paper.query.get(paper_id)
    paper.active_operation = None
    paper.active_operation_job_id = None
    paper.active_operation_started_at = None
    db.session.commit()


SAFE_BASH_COMMANDS = {"grep", "find", "wc", "cat", "head", "tail", "ls", "echo", "date", "pwd"}

MAX_RESULT_LENGTH = 6000

LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "logs", "chat_calls")
try:
    os.makedirs(LOGS_DIR, exist_ok=True)
except Exception as _e:
    logger.warning(f"could not create chat_calls log dir: {_e}")


def _log_chat_call(paper_id, conv_id, role, payload):
    """Append a JSONL line per chat call for tracing."""
    try:
        date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        sub = os.path.join(LOGS_DIR, str(paper_id or "_global"))
        os.makedirs(sub, exist_ok=True)
        fname = os.path.join(sub, f"{date_str}.jsonl")
        line = json.dumps(
            {
                "ts": datetime.datetime.utcnow().isoformat() + "Z",
                "conv_id": conv_id,
                "role": role,
                "payload": payload,
            },
            ensure_ascii=False,
        )
        with open(fname, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as e:
        logger.warning(f"_log_chat_call failed: {e}")


# Files / paths the AI must NEVER be able to read.
SENSITIVE_FILE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    "mydatabase.db",
    "requirements.txt.lock",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    ".gitconfig",
}
SENSITIVE_PATH_FRAGMENTS = (
    "/.git/",
    "/node_modules/",
    "/data/uploads/",
    "/data/exports/",
    "/.ssh/",
    "/certs/",
    "/__pycache__/",
)
ALLOWED_READ_ROOTS = (
    "/home/sirobo/papergenerator/backend/prompt/",
    "/home/sirobo/papergenerator/backend/template/",
    "/home/sirobo/papergenerator/frontend/src/",
)


_ALLOWED_MODELS = {None, "VIOLA-CHAT", "VIOLA-GENERATE"}


def execute_tool(tool_name, arguments, user_id, paper_id=None, model=None, conv_id=None):
    if model not in _ALLOWED_MODELS:
        model = None
    logger.info(
        f"[EXECUTE_TOOL] Entering execute_tool: tool={tool_name}, user_id={user_id}, paper_id={paper_id}, model={model}, conv_id={conv_id}, args={json.dumps(arguments, ensure_ascii=False)[:300]}"
    )
    _log_chat_call(
        paper_id,
        conv_id,
        "tool_call",
        {
            "tool": tool_name,
            "arguments": arguments,
            "model": model,
        },
    )
    try:
        result = _dispatch_tool(
            tool_name, arguments, user_id, paper_id, model=model, conv_id=conv_id
        )
        logger.info(f"[EXECUTE_TOOL_OK] tool={tool_name} result_preview={str(result)[:200]}")
        _log_chat_call(
            paper_id,
            conv_id,
            "tool_result",
            {
                "tool": tool_name,
                "result_preview": str(result)[:2000],
            },
        )
        return result
    except Exception as e:
        logger.exception(
            f"[EXECUTE_TOOL_ERROR] tool={tool_name} user_id={user_id} paper_id={paper_id}"
        )
        _log_chat_call(
            paper_id,
            conv_id,
            "tool_error",
            {
                "tool": tool_name,
                "error": str(e)[:2000],
            },
        )
        raise


def _dispatch_tool(tool_name, arguments, user_id, paper_id=None, model=None, conv_id=None):
    if model not in _ALLOWED_MODELS:
        model = None
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
            paper_id,
            user_id,
            arguments.get("prompt", ""),
            arguments.get("topic"),
            arguments.get("style"),
            arguments.get("use_attached_files", True),
            model=model,
        )
    elif tool_name == "RunSLR":
        return _run_slr_tool(
            paper_id,
            user_id,
            arguments.get("query", ""),
            arguments.get("sources"),
            int(arguments.get("top_k", 50) or 50),
            int(arguments.get("per_source", 60) or 60),
            arguments.get("year_from"),
            arguments.get("ai_model") or model or os.getenv("MODELGENERATE") or "VIOLA-GENERATE",
        )
    elif tool_name == "AddLiterature":
        kw = (arguments.get("keyword") or "").strip()
        if not kw:
            return "Error: keyword is required"
        return _run_slr_tool(
            paper_id,
            user_id,
            kw,
            None,
            int(arguments.get("top_k", 30) or 30),
            60,
            arguments.get("year_from"),
            os.getenv("MODELGENERATE") or "VIOLA-GENERATE",
        )
    elif tool_name == "GetLiterature":
        return _get_literature_tool(paper_id, user_id, int(arguments.get("limit", 50) or 50))
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
    elif tool_name == "ListMemory":
        return _list_memory(paper_id, user_id)
    elif tool_name == "DeleteMemory":
        return _delete_memory(paper_id, user_id, arguments.get("key", ""))
    elif tool_name == "SetCitationStyle":
        style = (arguments.get("style") or "IEEE").strip()
        if style not in {"ACS", "APA", "Chicago", "Harvard", "IEEE", "MLA", "Vancouver"}:
            style = "IEEE"
        msg = _save_memory(paper_id, user_id, "citation_style", style, kind="setting")
        if isinstance(msg, str) and msg.startswith("Error"):
            return msg
        return _propose("setting_saved", {"key": "citation_style", "value": style})
    elif tool_name == "SetLanguage":
        lang = (arguments.get("language") or "id").strip().lower()
        if lang not in {"id", "en"}:
            lang = "id"
        msg = _save_memory(paper_id, user_id, "paper_language", lang, kind="setting")
        if isinstance(msg, str) and msg.startswith("Error"):
            return msg
        return _propose("setting_saved", {"key": "paper_language", "value": lang})
    # ─── Tier-0 router + UI hint tools ─────────────────────────────────
    elif tool_name == "RouteIntent":
        # Classification tool. The chat blueprint reads the result, switches
        # the conversation's mode, and re-calls upstream with the new bundle.
        return {
            "kind": "route",
            "mode": (arguments.get("mode") or "casual"),
            "reasoning": arguments.get("reasoning", ""),
        }
    elif tool_name == "ProposeChips":
        chips = arguments.get("chips") or []
        if not isinstance(chips, list):
            chips = []
        # Wrap as a structured proposal so the chat blueprint can forward it
        # to the frontend through the SSE chips event.
        return _propose(
            "chips",
            {
                "chips": chips,
                "context_hint": arguments.get("context_hint", ""),
            },
        )
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
        return _propose(
            "section",
            {
                "section_index": arguments.get("section_index"),
                "title": arguments.get("title"),
                "content": arguments.get("content"),
            },
        )
    elif tool_name == "ProposeReference":
        return _propose(
            "reference",
            {
                "ref_index": arguments.get("ref_index"),
                "value": arguments.get("value", ""),
            },
        )
    elif tool_name == "ProposeJournal":
        return _propose("journal", {"value": arguments.get("journal", "")})
    elif tool_name == "RequestExportDocx":
        return _propose("export_docx", {})
    # ─── Revisi-mode proposals ──────────────────────────────────────────
    elif tool_name == "Paraphrase":
        return _propose_revisi(
            tool="Paraphrase",
            scope=arguments.get("scope"),
            section_index=arguments.get("section_index"),
            content_index=arguments.get("content_index"),
            text=arguments.get("text"),
            rewrite=arguments.get("rewrite", ""),
            style=arguments.get("style"),
        )
    elif tool_name == "FixGrammar":
        return _propose_revisi(
            tool="FixGrammar",
            scope=arguments.get("scope"),
            section_index=arguments.get("section_index"),
            content_index=arguments.get("content_index"),
            text=arguments.get("text"),
            rewrite=arguments.get("rewrite", ""),
        )
    elif tool_name == "Translate":
        return _propose_revisi(
            tool="Translate",
            scope=arguments.get("scope"),
            section_index=arguments.get("section_index"),
            content_index=arguments.get("content_index"),
            text=arguments.get("text"),
            rewrite=arguments.get("rewrite", ""),
            target_language=arguments.get("target_language"),
        )
    elif tool_name in ("Write", "Edit"):
        return "Tool not permitted in chat environment for security reasons."
    elif tool_name == "ClassifyFile":
        return _classify_file_tool(
            paper_id,
            user_id,
            arguments.get("file_id"),
            (arguments.get("kind") or "other"),
            (arguments.get("caption") or ""),
        )
    elif tool_name == "GenerateChart":
        return _generate_chart_tool(paper_id, user_id, arguments)
    elif tool_name == "GenerateImage":
        return _generate_image_tool(paper_id, user_id, arguments.get("prompt", ""))
    elif tool_name == "GetJobStatus":
        return _get_job_status_tool(arguments.get("job_id"), arguments.get("job_type"))
    elif tool_name == "UploadFile":
        return _upload_file_tool(paper_id, user_id, arguments.get("file_type", "document"))
    elif tool_name == "GetParagraphContext":
        return _get_paragraph_context(paper_id, user_id, arguments)
    elif tool_name == "ReviewLargeFile":
        return _review_large_file(paper_id, user_id, arguments)
    elif tool_name == "AskQuestions":
        qs = arguments.get("questions") or []
        if not isinstance(qs, list) or not qs:
            return "Error: questions array is required"
        validated = []
        for q in qs[:3]:
            if not isinstance(q, dict):
                continue
            opts = q.get("options") or []
            if isinstance(opts, list):
                opts = opts[:5]
            validated.append({
                "key": q.get("key", ""),
                "label": q.get("label", ""),
                "options": opts,
            })
        if not validated:
            return "Error: at least 1 valid question is required"
        return _propose("multi_question", {"questions": validated})
    elif tool_name == "StartWorkflow":
        return _start_workflow(paper_id, user_id)
    elif tool_name == "SaveWorkflowAnswers":
        return _save_workflow_answers(paper_id, user_id, arguments)
    elif tool_name == "ReviewPaper":
        return _propose(
            "review_plan",
            {
                "directive": arguments.get("directive", ""),
                "scope": arguments.get("scope", "whole"),
                "suggestions": [],
            },
        )
    elif tool_name == "ReviseData":
        return _propose("revise_data", {"directive": arguments.get("directive", "")})
    else:
        return f"Unknown tool: {tool_name}"


# Sentinel prefix that the frontend uses to detect a structured proposal
# payload coming back from a tool call.
PROPOSAL_PREFIX = "<<PROPOSAL>>"


def _propose(kind: str, fields: dict) -> str:
    """Wrap a proposal as a JSON payload prefixed with PROPOSAL_PREFIX."""
    payload = {"kind": kind, **fields}
    return PROPOSAL_PREFIX + json.dumps(payload, ensure_ascii=False)


def _start_workflow(paper_id, user_id):
    """Start the 9-phase workflow questionnaire. Returns all questions from Phase 0."""
    from workflows.tool import start_workflow

    result = start_workflow(paper_id, user_id)
    return _propose(result["kind"], {k: v for k, v in result.items() if k != "kind"})


def _save_workflow_answers(paper_id, user_id, arguments):
    """Save workflow answers and return next phase questions."""
    from workflows.tool import save_workflow_answers

    answers = arguments.get("answers") or {}
    if isinstance(answers, list):
        answers_list = answers
    else:
        # Convert dict to list of {key, value} pairs
        answers_list = [{"key": k, "value": v} for k, v in answers.items()]

    # Get current phase from workflow state
    from workflows.tool import _get_workflow_state
    workflow_state = _get_workflow_state(paper_id, user_id)
    current_phase = workflow_state.get("current_phase", "0")

    result = save_workflow_answers(paper_id, user_id, current_phase, answers_list)

    # Handle different result types
    if result["kind"] == "workflow_validation":
        # Phase 9 validation complete — auto-trigger paper generation
        from workflows.tool import _get_workflow_state as _gwfs
        wf_state = _gwfs(paper_id, user_id)
        all_answers = wf_state.get("answers", {})

        # Build the generation prompt from workflow answers (title is most specific)
        gen_prompt = (
            all_answers.get("title")
            or all_answers.get("topic")
            or all_answers.get("field", "Paper akademik")
        ).strip()

        gen_payload = None
        if gen_prompt:
            gen_str = _generate_full_paper(
                paper_id,
                user_id,
                gen_prompt,
                topic=all_answers.get("topic"),
                style=all_answers.get("citation_style"),
            )
            if isinstance(gen_str, str) and gen_str.startswith(PROPOSAL_PREFIX):
                try:
                    gen_payload = json.loads(gen_str[len(PROPOSAL_PREFIX):])
                except Exception:
                    pass

        validation_data = {k: v for k, v in result.items() if k != "kind"}
        if gen_payload:
            validation_data["generation"] = gen_payload
        return _propose("workflow_complete_generating", validation_data)
    elif result["kind"] == "workflow_continue":
        # Move to next phase - fetch questions for next phase
        from workflows.tool import start_workflow
        next_result = start_workflow(paper_id, user_id)
        # When the next phase has no card-ready questions (ai_generated fields
        # whose options haven't been filled yet), pass a text hint to the LLM
        # so it generates them via AskQuestions instead of rendering an empty card.
        questions = next_result.get("questions") or []
        if not questions and next_result.get("phase"):
            phase_name = next_result.get("phase_name", f"Phase {next_result['phase']}")
            return (
                f"✅ Jawaban disimpan. Lanjut ke {phase_name}. "
                f"Gunakan AskQuestions untuk menanyakan pertanyaan fase ini "
                f"(batch 3 pertanyaan) dengan opsi A–D yang relevan berdasarkan "
                f"profil pengguna. JANGAN tulis pertanyaan sebagai teks biasa."
            )
        return _propose(next_result["kind"], {k: v for k, v in next_result.items() if k != "kind"})
    elif result["kind"] == "workflow_complete":
        return result["message"]

    return "Workflow error: unexpected result type"


def _get_memory_value(paper_id, key):
    """Get a single memory value by key."""
    if not paper_id or not key:
        return None
    entry = ProjectMemory.query.filter_by(paper_id=paper_id, key=key).first()
    return entry.value if entry else None


def _propose_revisi(
    *,
    tool: str,
    scope,
    section_index,
    content_index,
    text,
    rewrite,
    target_language=None,
    style=None,
) -> str:
    """Wrap a revisi-mode proposal (Paraphrase / FixGrammar / Translate).

    The frontend (agent F2) will pick this up via the ``propose_revisi`` kind
    and render a side-by-side diff scoped to ``scope`` (paragraph / section /
    whole). All optional fields are dropped when ``None`` so the payload stays
    small.
    """
    payload = {
        "kind": "propose_revisi",
        "tool": tool,
        "scope": (scope or "paragraph"),
        "rewrite": rewrite or "",
    }
    if section_index is not None:
        try:
            payload["section_index"] = int(section_index)
        except (TypeError, ValueError):
            pass
    if content_index is not None:
        try:
            payload["content_index"] = int(content_index)
        except (TypeError, ValueError):
            pass
    if text:
        payload["text"] = text
    if target_language:
        payload["target_language"] = target_language
    if style:
        payload["style"] = style
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
    head = text[:max_len].encode("utf-8", errors="ignore")[:max_len]
    head = head.decode("utf-8", errors="ignore")
    return head + f"\n\n... [truncated, {len(text)} chars total]"


def _web_search(query):
    if not query:
        return "Error: query is required"
    try:
        resp = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"},
            timeout=10,
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
        if parsed.scheme not in ("http", "https"):
            return "Error: only http/https URLs are allowed."
        host = parsed.hostname or ""
        if not host:
            return "Error: invalid URL host."
        # Block SSRF to private / loopback / link-local ranges.
        try:
            for info in socket.getaddrinfo(host, None):
                ip = ipaddress.ip_address(info[4][0])
                if (
                    ip.is_private
                    or ip.is_loopback
                    or ip.is_link_local
                    or ip.is_multicast
                    or ip.is_reserved
                ):
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

        text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
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
        raw = search_all(
            query,
            limit_per_source=max(1, min(int(limit_per_source), 5)),
            sources=src_list,
            include_keyed=False,
        )
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

        cleaned.append(
            {
                "source": r.get("source"),
                "title": title,
                "authors": (r.get("authors") or [])[:6],
                "year": r.get("year"),
                "doi": doi,
                "url": url or (f"https://doi.org/{doi}" if doi else ""),
                "pdf_url": pdf,
                "abstract": (r.get("abstract") or "")[:600],
            }
        )

    if not cleaned:
        return (
            "(No valid, accessible papers found. Try a more specific query or different keywords.)"
        )

    # Cap output volume so the model context stays bounded
    cleaned = cleaned[:25]
    payload = {"query": query, "count": len(cleaned), "results": cleaned}
    return _truncate(json.dumps(payload, ensure_ascii=False, indent=2))


def _list_attached_files(paper_id, user_id):
    if not paper_id:
        return "No paper linked to this conversation."
    files = (
        PaperFile.query.filter_by(paper_id=paper_id, user_id=user_id)
        .order_by(PaperFile.created_at.desc())
        .all()
    )
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


_VALID_FILE_KINDS = {"data", "paper_read", "paper_slr", "template", "image", "other"}


def _classify_file_tool(paper_id, user_id, file_id, kind, caption):
    """Persist a user-confirmed classification for an attached file.

    The PaperFile model has no JSON metadata column today, so the role is
    stored as a ProjectMemory row keyed `file_kind:<file_id>` (paper-scoped,
    survives across chats) and the optional image caption as
    `file_caption:<file_id>`. Other tools can read these back if they need
    to know what role a file plays in this paper.
    """
    if not paper_id:
        return "Error: this chat is not linked to a paper."
    if not user_id:
        return "Error: not authenticated."
    if file_id is None:
        return "Error: file_id is required."
    try:
        fid = int(file_id)
    except (TypeError, ValueError):
        return "Error: file_id must be an integer."

    k = (kind or "other").strip().lower()
    if k not in _VALID_FILE_KINDS:
        k = "other"

    pf = PaperFile.query.filter_by(id=fid, paper_id=paper_id, user_id=user_id).first()
    if not pf:
        return _propose(
            "file_classified_error",
            {
                "file_id": fid,
                "error": "file not found or unauthorized",
            },
        )

    cap = (caption or "").strip()[:500]
    try:
        kind_key = f"file_kind:{fid}"
        kind_entry = ProjectMemory.query.filter_by(
            paper_id=paper_id,
            key=kind_key,
            conversation_id=None,
        ).first()
        if kind_entry:
            kind_entry.value = k
            kind_entry.kind = "file_meta"
        else:
            db.session.add(
                ProjectMemory(
                    paper_id=paper_id,
                    user_id=user_id,
                    key=kind_key,
                    value=k,
                    kind="file_meta",
                )
            )

        if cap:
            cap_key = f"file_caption:{fid}"
            cap_entry = ProjectMemory.query.filter_by(
                paper_id=paper_id,
                key=cap_key,
                conversation_id=None,
            ).first()
            if cap_entry:
                cap_entry.value = cap
                cap_entry.kind = "file_meta"
            else:
                db.session.add(
                    ProjectMemory(
                        paper_id=paper_id,
                        user_id=user_id,
                        key=cap_key,
                        value=cap,
                        kind="file_meta",
                    )
                )
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.exception("ClassifyFile commit failed")
        return _propose(
            "file_classified_error",
            {
                "file_id": fid,
                "error": f"persist failed: {e}",
            },
        )

    return _propose(
        "file_classified",
        {
            "file_id": fid,
            "file_kind": k,
            "caption": cap,
            "original_name": pf.original_name,
        },
    )


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
    """Render up to 50 LiteratureItem rows as a markdown block. Pinned +
    must_read first (with [MUST READ] marker). Returns "" when empty."""
    if not paper_id:
        return ""
    try:
        from database.models import LiteratureItem

        items = (
            db.session.query(LiteratureItem)
            .filter_by(paper_id=paper_id)
            .order_by(
                LiteratureItem.pinned.desc(),
                LiteratureItem.must_read.desc(),
                LiteratureItem.score_total.desc(),
                LiteratureItem.created_at.desc(),
            )
            .limit(50)
            .all()
        )
    except Exception:
        return ""
    if not items:
        return ""
    priority = [
        it for it in items if getattr(it, "pinned", False) or getattr(it, "must_read", False)
    ]
    rest = [it for it in items if it not in priority]
    ordered = priority + rest
    lines = [
        "## Literature catalog (use these as the actual reference list — "
        "cite by title/DOI; do not invent references not in this list)",
    ]
    for i, it in enumerate(ordered, 1):
        authors_list = it.authors or []
        authors = ", ".join(authors_list[:3])
        if len(authors_list) > 3:
            authors += " et al."
        marker = ""
        if getattr(it, "pinned", False) or getattr(it, "must_read", False):
            marker = "[MUST READ] "
        bits = [f"[L{i}] {marker}{it.title}"]
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
    n = len(ordered)
    lines.append(
        f"\nRULE: Use ONLY the entries above as the reference list. Do NOT "
        f"invent references not in this list. Number them [1]..[{n}] in "
        f"catalog order."
    )
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

    lines = ["## Project facts (from chat memory — pakai SEMUA fakta ini sebagai source of truth)"]
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


def _run_slr_tool(paper_id, user_id, query, sources, top_k, per_source, year_from, ai_model):
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
        from workers.slr_worker import enqueue_slr_job
    except Exception as e:
        return f"Error: SLR worker unavailable ({e})"

    src_list = None
    if isinstance(sources, list) and sources:
        src_list = [s for s in sources if isinstance(s, str)]

    try:
        year_from_int = int(year_from) if year_from else None
    except (TypeError, ValueError):
        year_from_int = None

    if ai_model not in {"VIOLA-CHAT", "VIOLA-GENERATE"}:
        ai_model = os.getenv("MODELGENERATE") or "VIOLA-GENERATE"

    job = enqueue_slr_job(
        paper_id=paper_id,
        user_id=int(user_id),
        query=q,
        sources=src_list,
        per_source=max(10, min(int(per_source), 100)),
        top_k=max(10, min(int(top_k), 100)),
        year_from=year_from_int,
        ai_summarize=True,
        ai_model=ai_model,
    )
    job_id = job.id

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
        from database.models import LiteratureItem
    except Exception as e:
        return f"Error: cannot read literature ({e})"
    items = (
        db.session.query(LiteratureItem)
        .filter_by(paper_id=paper_id)
        .order_by(
            LiteratureItem.pinned.desc(),
            LiteratureItem.score_total.desc(),
            LiteratureItem.created_at.desc(),
        )
        .limit(max(1, min(int(limit), 100)))
        .all()
    )
    if not items:
        return (
            "(Literature kosong. Pakai RunSLR untuk cari paper, atau import " "file PDF/DOCX dulu.)"
        )
    rows = []
    for it in items:
        authors = ", ".join((it.authors or [])[:4])
        rows.append(
            {
                "id": it.id,
                "title": it.title,
                "year": it.year,
                "authors": authors,
                "venue": it.venue,
                "doi": it.doi,
                "summary": (it.summary or it.abstract or "")[:400],
                "must_read": bool(it.must_read),
                "score": it.score_total,
            }
        )
    return _truncate(json.dumps(rows, ensure_ascii=False, indent=2))


def _generate_full_paper(
    paper_id, user_id, prompt, topic=None, style=None, use_attached_files=True, model=None
):
    """Kick off the same /api/generate-full job pipeline used by the dashboard,
    but from a chat tool call. Auto-injects extracted text from any files the
    user has attached to this paper. Also runs a quick planner pass first so
    the writer agent gets a concrete outline + scope (multi-stage cooperation
    on a single model)."""
    if model not in _ALLOWED_MODELS:
        model = None
    if not user_id:
        return "Error: not authenticated."
    prompt = (prompt or "").strip()
    if not prompt:
        return "Error: prompt is required (the paper title or topic)."

    allowed, reason = _check_paper_lock(paper_id, "generate")
    if not allowed:
        return f"Error: {reason}"

    api_key = os.getenv("AIOTOMASI_APIKEY")
    if not api_key:
        return "Error: AIOTOMASI_APIKEY is not configured on the server."

    # Pre-flight: require ≥20 literature rows (or at least one MUST READ pin)
    # before kicking off generation. Without enough SLR coverage the writer
    # falls back to fabricated references; surface a structured validation
    # error so the frontend can offer to run SLR first.
    if paper_id:
        try:
            from database.models import LiteratureItem

            n_lit = LiteratureItem.query.filter_by(paper_id=paper_id).count()
            n_must = LiteratureItem.query.filter_by(
                paper_id=paper_id,
                must_read=True,
            ).count()
        except Exception:
            logger.exception("GenerateFullPaper: literature pre-flight count failed")
            n_lit, n_must = 0, 0
        if n_lit < 20 and n_must == 0:
            return _propose(
                "validation_error",
                {
                    "error_code": "NEED_MORE_LITERATURE",
                    "message": (
                        f"Baru ada {n_lit} literatur. Minimal 20 paper SLR untuk "
                        f"generate berkualitas. Mau jalankan SLR otomatis dulu?"
                    ),
                    "current": n_lit,
                    "required": 20,
                },
            )

    # Collect attached file texts (capped) so the generator can use them as refs
    pdf_texts = []
    if use_attached_files and paper_id:
        files = (
            PaperFile.query.filter_by(paper_id=paper_id, user_id=user_id)
            .order_by(PaperFile.created_at.desc())
            .limit(5)
            .all()
        )
        for f in files:
            if f.extracted_text:
                pdf_texts.append(f"# {f.original_name}\n{f.extracted_text}")

    # PLANNER PASS — turn the chat history into a concrete outline before the
    # writer takes over. We snapshot project memory so the planner sees what
    # the user already locked in (target journal, methodology, etc.).
    memory_lines = ""
    citation_style = "IEEE"
    paper_language = "id"
    if paper_id:
        try:
            mems = ProjectMemory.query.filter_by(paper_id=paper_id).all()
            if mems:
                memory_lines = "\n".join(f"- {m.key}: {m.value}" for m in mems[:25])
                for m in mems:
                    if m.key == "citation_style" and (m.value or "").strip():
                        citation_style = m.value.strip()
                    elif m.key == "paper_language" and (m.value or "").strip():
                        paper_language = m.value.strip().lower()
        except Exception:
            memory_lines = ""

    # LITERATURE BLOCK — pull current LiteratureItem rows so the writer knows
    # which papers to cite. Pinned + must_read get prioritised.
    literature_block = _format_literature_block(paper_id)

    outline = _plan_outline(prompt, memory_lines, topic, style)

    # Resolve effective citation-style slug: explicit kwarg > memory > default.
    # The slug must match a file under prompt/style/<slug>.txt so
    # generate_paper_chunked._load_style_guide can load the right rules.
    effective_style = (style or "").strip() or citation_style or None

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
    # Output settings — these are saved via SetCitationStyle / SetLanguage and
    # carried through to every chunked stage. AI already knows the format
    # rules for each style; we don't inject style.txt content here.
    lang_label = "Bahasa Indonesia" if paper_language == "id" else "English"
    parts.append(
        f"## Output settings\n"
        f"- CITATION STYLE: {citation_style} (use this exact format for "
        f"in-text citations and the reference list — you already know it).\n"
        f"- OUTPUT LANGUAGE: {lang_label} (write all prose, headings, "
        f"figure/table captions in this language)."
    )
    custom_prompt = "\n\n".join(parts)

    # Run inside the existing app context so Flask's job machinery is available
    try:
        from app import _job_create, _run_generate_full_job, app
    except Exception as e:
        return f"Error: cannot import app job runner ({e})"

    job_id = uuid.uuid4().hex[:12]
    try:
        with app.app_context():
            # Pass paper_id so the job row is bound to this paper. Falls
            # back to the legacy 3-arg signature for environments where
            # app._job_create has not been updated yet (Agent D will land
            # the matching change).
            try:
                _job_create(job_id, int(user_id), prompt, paper_id=paper_id)
            except TypeError:
                _job_create(job_id, int(user_id), prompt)
        thread = threading.Thread(
            target=_run_generate_full_job,
            args=(job_id, prompt, int(user_id)),
            kwargs={
                "topic": topic,
                "style": effective_style,
                "pdf_texts": pdf_texts,
                "custom_prompt": custom_prompt,
                "paper_id": paper_id,
            },
            daemon=True,
        )
        _set_paper_lock(paper_id, "generating", job_id)
        thread.start()
        logger.info("paper.generate prompt=%s", prompt[:80])
    except Exception as e:
        # Cleanup the AiJob row so the paper isn't stuck with a phantom 'pending' job
        try:
            with app.app_context():
                from database.models import AiJob

                row = AiJob.query.get(job_id)
                if row:
                    row.status = "error"
                    row.error = f"start failed: {e}"[:500]
                    db.session.commit()
        except Exception:
            pass
        _clear_paper_lock(paper_id)
        return f"Error: starting job failed ({e})"

    # Best-effort: tell the chat blueprint that this paper now has an
    # in-flight generation job so its /active-job endpoint can surface it.
    # Only registered AFTER thread.start() so the registry stays consistent
    # with worker state.
    try:
        from api.chat_bp import register_active_job

        register_active_job(paper_id, job_id)
    except Exception:
        pass  # registry not available — non-fatal

    # Return a structured payload so the frontend can show the job spinner
    payload = {
        "kind": "paper_progress",
        "job_id": job_id,
        "prompt": prompt,
        "topic": topic,
        "style": effective_style,
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
    model = os.getenv("MODELCHAT") or "VIOLA-CHAT"
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
    (1000, "M"),
    (900, "CM"),
    (500, "D"),
    (400, "CD"),
    (100, "C"),
    (90, "XC"),
    (50, "L"),
    (40, "XL"),
    (10, "X"),
    (9, "IX"),
    (5, "V"),
    (4, "IV"),
    (1, "I"),
)


def _to_roman(num: int) -> str:
    out = ""
    for v, s in _ROMAN_PAIRS:
        while num >= v:
            out += s
            num -= v
    return out


def _walk_content_for_numbering(
    content_list, fig_idx, tbl_idx, eq_idx, figs, tbls, eqs, section_title
):
    """Walk a content list (already shape-normalized: list of dicts with id)
    and append entries to figs/tbls/eqs lists. Returns updated indices."""
    for item in content_list or []:
        if not isinstance(item, dict):
            continue
        kind = item.get("id")
        if kind == "gambar":
            figs.append(
                {
                    "fig_number": fig_idx,
                    "label": f"Fig. {fig_idx}",
                    "title": item.get("Title") or "",
                    "section": section_title,
                    "has_path": bool(item.get("Path")),
                    "prompt": (item.get("Prompt") or "")[:200],
                }
            )
            fig_idx += 1
        elif kind == "tabel":
            tbls.append(
                {
                    "table_number": tbl_idx,
                    "label": f"Table {_to_roman(tbl_idx)}",
                    "title": item.get("Title") or "",
                    "section": section_title,
                }
            )
            tbl_idx += 1
        elif kind == "rumus":
            eqs.append(
                {
                    "eq_number": eq_idx,
                    "label": f"Eq. ({eq_idx})",
                    "section": section_title,
                    "latex": (item.get("latex") or "")[:200],
                }
            )
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
                sec.get("content"), fig_idx, tbl_idx, eq_idx, figs, tbls, eqs, title
            )
            for sub in sec.get("subsections") or []:
                fig_idx, tbl_idx, eq_idx = _walk_content_for_numbering(
                    sub.get("content"),
                    fig_idx,
                    tbl_idx,
                    eq_idx,
                    figs,
                    tbls,
                    eqs,
                    f"{title} — {sub.get('title','')}",
                )
    else:
        skeys = sorted(
            (
                k
                for k in data.keys()
                if isinstance(k, str) and k.startswith("section") and k[7:].isdigit()
            ),
            key=lambda k: int(k[7:]),
        )
        for sk in skeys:
            sec = data.get(sk) or {}
            if not isinstance(sec, dict):
                continue
            title = sec.get("title", "")
            fig_idx, tbl_idx, eq_idx = _walk_content_for_numbering(
                sec.get("content"), fig_idx, tbl_idx, eq_idx, figs, tbls, eqs, title
            )
            for subk in sorted(
                k for k in sec.keys() if isinstance(k, str) and k.startswith(sk) and k != sk
            ):
                sub = sec.get(subk) or {}
                if not isinstance(sub, dict):
                    continue
                fig_idx, tbl_idx, eq_idx = _walk_content_for_numbering(
                    sub.get("content"),
                    fig_idx,
                    tbl_idx,
                    eq_idx,
                    figs,
                    tbls,
                    eqs,
                    f"{title} — {sub.get('title','')}",
                )

    return _truncate(
        json.dumps(
            {"figures": figs, "tables": tbls, "equations": eqs},
            ensure_ascii=False,
            indent=2,
        )
    )


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
        with open(real_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return _truncate(content)
    except Exception as e:
        return f"Read error: {str(e)}"


def _safe_bash(command):
    if not command:
        return "Error: command is required"
    # Reject anything that looks like shell metacharacters BEFORE parsing.
    forbidden = (";", "&&", "||", "|", "`", "$(", "$\\", ">", "<", "\n", "\r")
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
        if any(low.endswith("/" + s) or low == s for s in SENSITIVE_FILE_NAMES):
            return "Error: argument references a restricted file."
        if arg.startswith("/") and not arg.startswith("/home/sirobo/papergenerator/"):
            return "Error: only paths inside the project are allowed."
    try:
        result = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            timeout=10,
            cwd="/home/sirobo/papergenerator",
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
    entries = (
        ProjectMemory.query.filter_by(paper_id=paper_id)
        .order_by(ProjectMemory.updated_at.desc())
        .all()
    )
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
    entries = (
        ProjectMemory.query.filter_by(paper_id=paper_id)
        .order_by(ProjectMemory.updated_at.desc())
        .all()
    )
    if not entries:
        return ""
    lines = [f"- [{e.kind}] {e.key}: {e.value}" for e in entries]
    return "\n".join(lines)


def _generate_chart_tool(paper_id, user_id, args):
    """Wrapper around chart_generator.generate_chart that persists the result
    as a PaperImage row so it can be referenced from a section just like any
    other figure."""
    if not paper_id:
        return "Error: this chat is not linked to a paper."
    if not user_id:
        return "Error: not authenticated."

    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return "Error: paper not found"

    try:
        from core.chart_generator import ChartSpec, generate_chart
        from paper_generation.utils import safe_paper_dir
    except Exception as e:
        return f"Error: chart generator unavailable ({e})"

    try:
        spec_kwargs = {
            "kind": args.get("kind"),
            "title": args.get("title") or "",
            "xlabel": args.get("xlabel") or "",
            "ylabel": args.get("ylabel") or "",
            "data": args.get("data") or [],
            "series_labels": args.get("series_labels") or [],
            "x_data": args.get("x_data"),
        }
        spec = ChartSpec(**spec_kwargs)
    except Exception as e:
        return f"Error: invalid chart spec ({e})"

    try:
        chart_path = generate_chart(paper_id, spec)
    except Exception as e:
        return f"Error: chart generation failed ({e})"

    try:
        paper_dir = safe_paper_dir(paper_id)
        if paper_dir is None:
            return "Error: invalid paper id (path resolution failed)"
        paper_dir.mkdir(parents=True, exist_ok=True)

        src = os.path.abspath(chart_path)
        ext = os.path.splitext(src)[1].lower() or ".png"
        fname = f"{uuid.uuid4().hex}{ext}"
        dest = paper_dir / fname
        try:
            import shutil

            shutil.copyfile(src, str(dest))
        except Exception as e:
            return f"Error: persisting chart failed ({e})"

        img = PaperImage(
            paper_id=paper_id,
            user_id=int(user_id),
            filename=fname,
            original_name=f"chart_{spec.kind}_{fname}",
            file_path=f"{paper_id}/{fname}",
        )
        db.session.add(img)
        db.session.commit()
        img_id = img.id
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return f"Error: persisting chart failed ({e})"

    return PROPOSAL_PREFIX + json.dumps(
        {
            "kind": "chart_proposal",
            "image_id": img_id,
            "filename": fname,
            "url": f"/api/images/{paper_id}/{fname}",
            "spec": {"kind": args.get("kind"), "title": args.get("title")},
        },
        ensure_ascii=False,
    )


def _get_paragraph_context(paper_id, user_id, args):
    """Token-efficient context for paragraph-scoped revisions: returns the
    target paragraph plus immediate neighbors plus a one-line outline."""
    import re as _re

    if not paper_id:
        return "No paper linked to this conversation."
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return "Error: paper not found"
    try:
        s_idx = int(args["section_index"]) - 1
        c_idx = int(args["content_index"])
    except (KeyError, ValueError, TypeError):
        return "Error: section_index and content_index must be integers"

    sections = (paper.data or {}).get("sections") or []
    if s_idx < 0 or s_idx >= len(sections):
        return f"Error: section_index out of range (have {len(sections)})"
    sec = sections[s_idx]
    content = sec.get("content") or []
    if c_idx < 0 or c_idx >= len(content):
        return f"Error: content_index out of range (section has {len(content)} items)"

    target = content[c_idx] if isinstance(content[c_idx], dict) else {}
    window = max(0, int(args.get("neighbor_window", 1) or 0))
    cit_re = _re.compile(r"\[\d+\]|\(\w+,\s*\d{4}\)")
    fig_re = _re.compile(r"Fig\.?\s*\d+|Table\s*[IVX0-9]+|Eq\.?\s*\(?\d+\)?", _re.I)
    text = target.get("text") or ""

    outline = []
    for i, ci in enumerate(content):
        if not isinstance(ci, dict):
            continue
        snippet = (ci.get("text") or "")[:80]
        marker = " ← target" if i == c_idx else ""
        outline.append(f"P{i} — {snippet}{marker}")

    try:
        mems = {m.key: m.value for m in ProjectMemory.query.filter_by(paper_id=paper_id).all()}
    except Exception:
        mems = {}

    prev_text = ""
    next_text = ""
    if window > 0:
        if c_idx > 0 and isinstance(content[c_idx - 1], dict):
            prev_text = content[c_idx - 1].get("text") or ""
        if c_idx + 1 < len(content) and isinstance(content[c_idx + 1], dict):
            next_text = content[c_idx + 1].get("text") or ""

    payload = {
        "section_meta": {
            "index": s_idx + 1,
            "title": sec.get("title", ""),
            "neighbor_titles": {
                "prev": sections[s_idx - 1].get("title") if s_idx > 0 else None,
                "next": sections[s_idx + 1].get("title") if s_idx + 1 < len(sections) else None,
            },
            "section_outline": outline,
        },
        "target": {
            "section_index": s_idx + 1,
            "content_index": c_idx,
            "kind": target.get("id", "text"),
            "text": text,
        },
        "neighbors": {
            "prev": prev_text,
            "next": next_text,
        },
        "citations_in_target": list(set(cit_re.findall(text))),
        "fig_table_refs": list(set(fig_re.findall(text))),
        "constraints": {
            "language": mems.get("paper_language", "id"),
            "citation_style": mems.get("citation_style", "IEEE"),
        },
    }
    if args.get("include_paper_meta"):
        payload["paper_meta"] = {"title": paper.title or ""}
    return _truncate(json.dumps(payload, ensure_ascii=False))


def _review_large_file(paper_id, user_id, args):
    """For attached files >3000 words, return head/tail preview plus a
    proposal asking the user (via ProposeChips) which kind of content to
    extract. For smaller files, fall back to ReadAttachedFile semantics."""
    if not paper_id:
        return "No paper linked to this conversation."
    file_id = args.get("file_id")
    if file_id is None:
        return "Error: file_id is required."
    try:
        fid = int(file_id)
    except (TypeError, ValueError):
        return "Error: file_id must be an integer."

    f = PaperFile.query.filter_by(id=fid, paper_id=paper_id, user_id=user_id).first()
    if not f:
        return f"File id={fid} not found in this paper."

    text = f.extracted_text or ""
    words = text.split()
    word_count = len(words)
    if word_count <= 3000:
        return _read_attached_file(paper_id, user_id, fid)

    head = " ".join(words[:200])
    tail = " ".join(words[-200:])
    return PROPOSAL_PREFIX + json.dumps(
        {
            "kind": "file_review",
            "file_id": fid,
            "filename": f.original_name or f.filename,
            "word_count": word_count,
            "head": head,
            "tail": tail,
            "suggested_kinds": ["data", "methods", "results", "abstract", "literature"],
            "needs_user_pick": True,
        },
        ensure_ascii=False,
    )


def _generate_image_tool(paper_id, user_id, prompt):
    """Enqueue an AI image generation job via Gemini worker pool.

    Returns a job_id that the frontend can poll via /api/image-jobs/<id>.
    When the job completes, the worker persists a PaperImage row and sets
    image_id on the job.
    """
    if not paper_id:
        return "Error: this chat is not linked to a paper."
    if not user_id:
        return "Error: not authenticated."

    prompt = (prompt or "").strip()
    if not prompt:
        return "Error: prompt is required (describe the image to generate)."

    if len(prompt) > 2000:
        return "Error: prompt too long (max 2000 characters)."

    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return "Error: paper not found."

    try:
        from database.models import ImageGenJob
    except Exception as e:
        return f"Error: ImageGenJob model unavailable ({e})"

    # Check inflight limit
    inflight = ImageGenJob.query.filter(
        ImageGenJob.user_id == user_id,
        ImageGenJob.status.in_(["queued", "running"]),
    ).count()
    if inflight >= 12:
        return "Error: Maximum 12 active image jobs. Please wait for some to complete."

    job_id = uuid.uuid4().hex
    job = ImageGenJob(
        id=job_id,
        user_id=user_id,
        paper_id=paper_id,
        prompt=prompt,
        status="queued",
    )
    db.session.add(job)
    db.session.commit()

    # Best-effort: submit to worker pool immediately
    try:
        from workers.image_worker import submit_now
        submit_now(job_id)
    except Exception:
        logger.warning("submit_now failed (job will run via dispatcher poll)")

    return _propose(
        "image_job",
        {
            "job_id": job_id,
            "prompt": prompt,
            "status": "queued",
        },
    )


def _get_job_status_tool(job_id, job_type=None):
    """Check status of any background job (paper generation, SLR, or image).

    Args:
        job_id: The job ID to check
        job_type: Optional hint: 'paper'|'slr'|'image'. If not provided, tries all.

    Returns:
        JSON with job status, progress, stage, error (if any).
    """
    if not job_id:
        return "Error: job_id is required."

    job_id = str(job_id).strip()
    if not job_id:
        return "Error: job_id cannot be empty."

    # Try to find the job in the appropriate table
    job = None
    job_kind = None

    if job_type == "paper" or job_type is None:
        try:
            from database.models import AiJob
            job = AiJob.query.get(job_id)
            if job:
                job_kind = "paper"
        except Exception:
            pass

    if not job and (job_type == "slr" or job_type is None):
        try:
            from database.models import SlrJob
            job = SlrJob.query.get(job_id)
            if job:
                job_kind = "slr"
        except Exception:
            pass

    if not job and (job_type == "image" or job_type is None):
        try:
            from database.models import ImageGenJob
            job = ImageGenJob.query.get(job_id)
            if job:
                job_kind = "image"
        except Exception:
            pass

    if not job:
        return f"Error: Job {job_id} not found."

    # Build response based on job type
    response = {
        "job_id": job_id,
        "job_type": job_kind,
        "status": job.status,
    }

    if hasattr(job, "progress"):
        response["progress"] = job.progress
    if hasattr(job, "stage"):
        response["stage"] = job.stage or ""
    if hasattr(job, "progress_message"):
        response["progress_message"] = job.progress_message or ""
    if hasattr(job, "error") and job.error:
        response["error"] = job.error
    if hasattr(job, "image_id") and job.image_id:
        response["image_id"] = job.image_id
    if hasattr(job, "worker") and job.worker:
        response["worker"] = job.worker

    # Add timestamps
    if hasattr(job, "started_at") and job.started_at:
        response["started_at"] = job.started_at.isoformat()
    if hasattr(job, "finished_at") and job.finished_at:
        response["finished_at"] = job.finished_at.isoformat()
    if hasattr(job, "updated_at") and job.updated_at:
        response["updated_at"] = job.updated_at.isoformat()

    return _truncate(json.dumps(response, ensure_ascii=False, indent=2))


def _upload_file_tool(paper_id, user_id, file_type="document"):
    """Return the upload URL for attaching files to this paper.

    Args:
        paper_id: The paper to attach files to
        user_id: Current user
        file_type: 'document' (PDF/DOCX) or 'image' (PNG/JPG)

    Returns:
        Upload URL and instructions.
    """
    if not paper_id:
        return "Error: this chat is not linked to a paper."
    if not user_id:
        return "Error: not authenticated."

    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return "Error: paper not found."

    file_type = (file_type or "document").strip().lower()

    if file_type == "image":
        upload_url = f"/api/images/{paper_id}/images/upload"
        accepted_formats = "PNG, JPG, JPEG"
        max_size = "10MB"
    else:
        upload_url = f"/api/files/{paper_id}/upload"
        accepted_formats = "PDF, DOCX, TXT, MD"
        max_size = "50MB"

    return _propose(
        "upload_url",
        {
            "upload_url": upload_url,
            "paper_id": paper_id,
            "file_type": file_type,
            "accepted_formats": accepted_formats,
            "max_size": max_size,
            "method": "POST",
            "instructions": (
                f"Upload {file_type}s to {upload_url} via POST with multipart/form-data. "
                f"Accepted formats: {accepted_formats}. Max size: {max_size}."
            ),
        },
    )


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
                "style": {
                    "type": "string",
                    "description": "Optional citation-style slug from /api/styles.",
                },
                "use_attached_files": {"type": "boolean", "description": "Default true."},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "RunSLR",
        "description": (
            "Trigger a Systematic Literature Review (SLR) job that fetches papers from "
            "academic APIs (OpenAlex, Crossref, Semantic Scholar, arXiv, DBLP, Europe PMC, "
            "IEEE, SINTA/Garuda), ranks them with SBERT + citation + recency + venue quality, "
            "AI-summarizes the top results, and persists them to the Literature tab as "
            "LiteratureItem rows. Use this whenever the user asks for literature review, "
            "tinjauan pustaka, studi pustaka, systematic review, related work, kumpulkan "
            "referensi, or wants to populate the Literature tab. Do NOT use SearchPapers "
            "for these requests — RunSLR is the persistent path; SearchPapers is only for "
            "ad-hoc inline lookups when the user explicitly wants results shown in chat."
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
                "top_k": {
                    "type": "integer",
                    "description": "How many to summarize (default 50, max 100).",
                },
                "per_source": {
                    "type": "integer",
                    "description": "Max results per source (default 60).",
                },
                "year_from": {"type": "integer", "description": "Optional cutoff year."},
                "ai_model": {
                    "type": "string",
                    "description": "VIOLA-CHAT|VIOLA-GENERATE. Default VIOLA-GENERATE.",
                },
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
        "name": "SetCitationStyle",
        "description": (
            "Save the user's chosen citation style for this paper. The AI "
            "already knows the format conventions (ACS, APA, Chicago, "
            "Harvard, IEEE, MLA, Vancouver) — no style file is injected. "
            "Call this after the user picks via ProposeChips."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "style": {
                    "type": "string",
                    "enum": ["ACS", "APA", "Chicago", "Harvard", "IEEE", "MLA", "Vancouver"],
                },
            },
            "required": ["style"],
        },
    },
    {
        "name": "SetLanguage",
        "description": "Save the user's chosen output language for this paper (id = Bahasa Indonesia, en = English).",
        "input_schema": {
            "type": "object",
            "properties": {
                "language": {
                    "type": "string",
                    "enum": ["id", "en"],
                    "description": "id = Bahasa Indonesia, en = English",
                },
            },
            "required": ["language"],
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
    {
        "name": "RouteIntent",
        "description": (
            "Classify the user's intent into a workflow mode. Call this FIRST "
            "when the conversation's mode is unknown (tier-0) or when the user "
            "switches context (e.g. from discovery planning to editing an "
            "existing section). The chat backend swaps in a mode-specific "
            "system prompt + tool subset right after this call. Do NOT use "
            "this tool unless you actually need to change mode."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["discovery", "slr", "edit", "rapikan", "memory", "casual", "revisi"],
                    "description": (
                        "discovery for 7-step paper planning; slr for "
                        "literature search; edit for paper editing; rapikan "
                        "for renumbering Fig/Table/Eq; revisi for revising a "
                        "finished paper (abstract/section/data/paraphrase/"
                        "grammar/translate); memory for memory management; "
                        "casual for free chat."
                    ),
                },
                "reasoning": {
                    "type": "string",
                    "description": "One-line explanation of why this mode fits.",
                },
            },
            "required": ["mode"],
        },
    },
    {
        "name": "ProposeChips",
        "description": (
            "Show the user 2-6 clickable option chips beside your message. "
            "Each chip becomes the user's next reply when clicked. Use this "
            "for question-with-options patterns (e.g. the 7-step discovery) "
            "INSTEAD of writing 1) 2) 3) inline. Frontend renders both the "
            "chip buttons and a free-text fallback."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "chips": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 6,
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {
                                "type": "string",
                                "description": "Short text shown on the chip.",
                            },
                            "value": {
                                "type": "string",
                                "description": "The exact reply submitted when clicked.",
                            },
                        },
                        "required": ["label", "value"],
                    },
                },
                "context_hint": {
                    "type": "string",
                    "description": "Optional one-line prompt rendered above the chips.",
                },
            },
            "required": ["chips"],
        },
    },
    {
        "name": "Paraphrase",
        "description": (
            "Paraphrase a paragraph, section, or whole paper. Returns a "
            "proposal the user accepts/rejects via the diff UI. Read the "
            "target section with GetPaperSection FIRST so the rewrite stays "
            "faithful to surrounding context."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["paragraph", "section", "whole"],
                    "description": "What to paraphrase.",
                },
                "section_index": {
                    "type": "integer",
                    "description": "1-5 for sections; required if scope=section or paragraph.",
                },
                "content_index": {
                    "type": "integer",
                    "description": "Index of the content box within the section; required if scope=paragraph.",
                },
                "text": {
                    "type": "string",
                    "description": "The original text to paraphrase.",
                },
                "rewrite": {
                    "type": "string",
                    "description": "The paraphrased text the AI proposes.",
                },
                "style": {
                    "type": "string",
                    "description": "Optional: 'formal', 'concise', 'simple'.",
                },
            },
            "required": ["scope", "rewrite"],
        },
    },
    {
        "name": "FixGrammar",
        "description": (
            "Fix grammar in a paragraph, section, or the whole paper. "
            "Returns a proposal for the user to accept/reject. Preserve the "
            "author's voice; only correct grammar/spelling/punctuation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["paragraph", "section", "whole"],
                },
                "section_index": {"type": "integer"},
                "content_index": {"type": "integer"},
                "text": {"type": "string"},
                "rewrite": {"type": "string"},
            },
            "required": ["scope", "rewrite"],
        },
    },
    {
        "name": "Translate",
        "description": (
            "Translate a paragraph, section, or the whole paper to a target "
            "language. Returns a proposal. Keep technical terms and citation "
            "markers ([1], Fig. 2, Eq. (3)) intact."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["paragraph", "section", "whole"],
                },
                "section_index": {"type": "integer"},
                "content_index": {"type": "integer"},
                "text": {"type": "string"},
                "target_language": {
                    "type": "string",
                    "description": "ISO code or readable label: 'id', 'en', 'Indonesian', 'English'.",
                },
                "rewrite": {"type": "string"},
            },
            "required": ["scope", "target_language", "rewrite"],
        },
    },
    {
        "name": "ClassifyFile",
        "description": (
            "Mark an uploaded file's role for this paper. Call this AFTER the "
            "user picks via AskQuestions/ProposeChips. Canonical kinds + "
            "default chip labels (Bahasa Indonesia):\n"
            "  - paper_slr    'Paper review (masuk SLR)'\n"
            "  - paper_read   'Paper jadi (retemplating, skip SLR)'\n"
            "  - data         'Data file (tabel/grafik)'\n"
            "  - image        'Gambar (figure paper)'\n"
            "  - template     'Template jurnal'\n"
            "  - other        fallback when none fits\n"
            "If kind=image, also pass the user's caption. Files classified as "
            "paper_read MUST be skipped from SLR; tell the user the file is "
            "marked for retemplating only. Files classified as paper_slr with "
            ">3000 words should be paired with ReviewLargeFile so the user "
            "picks which sections (data/methods/results/abstract/literature) "
            "to extract — one file at a time. The classification persists "
            "across chats."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {
                    "type": "integer",
                    "description": "PaperFile id (use ListAttachedFiles to find).",
                },
                "kind": {
                    "type": "string",
                    "enum": ["data", "paper_read", "paper_slr", "template", "image", "other"],
                },
                "caption": {
                    "type": "string",
                    "description": "If kind=image, the user's caption text.",
                },
            },
            "required": ["file_id", "kind"],
        },
    },
    {
        "name": "GenerateChart",
        "description": "Generate a matplotlib chart from data and persist it as a PaperImage. Use this for Section 4 (Results) figures when the user has confirmed the chart kind and data shape. After this returns, propose a ProposeSection that references Fig. N where the new chart should appear.",
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["line", "bar", "scatter", "hist", "box", "heatmap", "pie"],
                },
                "title": {"type": "string"},
                "xlabel": {"type": "string"},
                "ylabel": {"type": "string"},
                "data": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}},
                "series_labels": {"type": "array", "items": {"type": "string"}},
                "x_data": {"type": "array"},
            },
            "required": ["kind", "title", "data"],
        },
    },
    {
        "name": "GenerateImage",
        "description": (
            "Generate an AI image via Gemini worker pool. Use this when the user "
            "requests an illustration, diagram, or visual that cannot be created "
            "with GenerateChart. Returns a job_id that the frontend polls. When "
            "complete, the image is persisted as a PaperImage and can be referenced "
            "in sections. Max 12 concurrent jobs per user."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Detailed description of the image to generate (max 2000 chars).",
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "GetJobStatus",
        "description": (
            "Check the status of any background job (paper generation, SLR, or image). "
            "Returns status (queued|running|done|error|cancelled), progress (0-100), "
            "stage, error message (if any), and timestamps. Use this to check on jobs "
            "started by GenerateFullPaper, RunSLR, or GenerateImage."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "The job ID returned by GenerateFullPaper, RunSLR, or GenerateImage.",
                },
                "job_type": {
                    "type": "string",
                    "enum": ["paper", "slr", "image"],
                    "description": "Optional hint to speed up lookup. If omitted, tries all types.",
                },
            },
            "required": ["job_id"],
        },
    },
    {
        "name": "UploadFile",
        "description": (
            "Get the upload URL for attaching files to this paper. Returns the "
            "endpoint URL, accepted formats, and max size. Use this when the user "
            "wants to upload documents (PDF/DOCX/TXT/MD) or images (PNG/JPG). "
            "The frontend handles the actual upload via multipart/form-data POST."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_type": {
                    "type": "string",
                    "enum": ["document", "image"],
                    "description": "Type of file to upload. Default: document.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "GetParagraphContext",
        "description": "Get a single paragraph plus its immediate neighbors and a section outline. Use this BEFORE Paraphrase/FixGrammar/Translate when the scope is a single paragraph. Returns ~80% fewer tokens than GetPaperSection while still giving you context to preserve voice, citations, and figure references.",
        "input_schema": {
            "type": "object",
            "properties": {
                "section_index": {
                    "type": "integer",
                    "description": "1-indexed section number (1..5)",
                },
                "content_index": {
                    "type": "integer",
                    "description": "0-indexed position in section.content array",
                },
                "neighbor_window": {
                    "type": "integer",
                    "default": 1,
                    "description": "How many paragraphs above/below to include",
                },
                "include_paper_meta": {"type": "boolean", "default": False},
            },
            "required": ["section_index", "content_index"],
        },
    },
    {
        "name": "ReviewLargeFile",
        "description": "Review an attached file >3000 tokens. Returns metadata + length info + first/last paragraphs only, telling AI to ask user (via ProposeChips) which kinds to extract: data, methods, results, abstract, literature. Pair with ProposeChips so user picks what to keep.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "integer"},
            },
            "required": ["file_id"],
        },
    },
    {
        "name": "AskQuestions",
        "description": "Ask the user exactly 3 related multiple-choice questions at once. Each question MUST have exactly 4 chip options; the user can also type a free-text answer. Use for batched fact gathering in discovery/revisi mode. Frontend renders MultiQuestionCard with uniform layout. After user answers, auto-memory persists each (key, value). ALWAYS send 3 questions per call, logically connected.",
        "input_schema": {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 3,
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {
                                "type": "string",
                                "description": "Memory key, e.g. jurusan, topik, metode.",
                            },
                            "label": {
                                "type": "string",
                                "description": "Question text in user's language.",
                            },
                            "options": {
                                "type": "array",
                                "minItems": 4,
                                "maxItems": 4,
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "label": {"type": "string"},
                                        "value": {"type": "string"},
                                    },
                                    "required": ["label", "value"],
                                },
                            },
                        },
                        "required": ["key", "label", "options"],
                    },
                },
            },
            "required": ["questions"],
        },
    },
    {
        "name": "ReviewPaper",
        "description": "Run a holistic review of the paper per the user's directive. Returns a list of suggested edits the user can accept individually. Use this when the user asks for a comprehensive revisi/review.",
        "input_schema": {
            "type": "object",
            "properties": {
                "directive": {
                    "type": "string",
                    "description": "User's review directive (e.g., 'tighten language', 'check coherence', 'verify citations').",
                },
                "scope": {
                    "type": "string",
                    "enum": ["whole", "section1", "section2", "section3", "section4", "section5"],
                    "default": "whole",
                },
            },
            "required": ["directive"],
        },
    },
    {
        "name": "ReviseData",
        "description": "Trigger Section 4 (Results) data revision. Use this when the user wants to fix data, regenerate the chart from new numbers, or re-cast the analysis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "directive": {"type": "string"},
            },
            "required": ["directive"],
        },
    },
    {
        "name": "AddLiterature",
        "description": "Add new literature via SLR. Reads existing GetLiterature first, then enqueues a new RunSLR job with the provided keyword(s). Use when the user wants to expand the reference list.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string"},
                "year_from": {"type": "integer"},
                "top_k": {"type": "integer", "default": 30},
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "StartWorkflow",
        "description": "Start the 9-phase guided questionnaire for building a paper from scratch. Returns the first batch of 3 questions (Phase 0: progress, data readiness, team size). Use when user wants to generate a full paper and has no existing history.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "SaveWorkflowAnswers",
        "description": "Save the user's workflow answers and return the next batch of 3 questions. Call this after receiving answers from a workflow MultiQuestionCard. Automatically advances to the next phase when current phase questions are complete.",
        "input_schema": {
            "type": "object",
            "properties": {
                "answers": {
                    "type": "object",
                    "description": "Dictionary of key-value pairs from the user's answers (e.g. {\"progress_level\": \"A\", \"data_readiness\": \"B\", \"team_size\": \"A\"}).",
                },
            },
            "required": ["answers"],
        },
    },
]
