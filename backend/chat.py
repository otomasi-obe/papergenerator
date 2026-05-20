"""
Chat Blueprint
===============
Multi-chat per paper, project-scoped memory, SSE streaming with tool execution.

Data model:
    Paper (1) ─── (many) Conversation (chat thread) ─── (many) ChatMessage
    Paper (1) ─── (many) ProjectMemory (shared across all chats inside the paper)
"""

import json
import os
import logging
import uuid
import requests
from flask import Blueprint, request, Response, stream_with_context
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import db, Conversation, ChatMessage, Paper, ProjectMemory
from chat_tools import execute_tool, CHAT_TOOLS, get_memory_summary
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)
chat_bp = Blueprint('chat', __name__)

_AIOTOMASI_API_BASE = os.getenv("AIOTOMASI_API") or ""
API_URL = (_AIOTOMASI_API_BASE.rstrip('/') + "/chat/completions") if _AIOTOMASI_API_BASE else ""
API_KEY = os.getenv("AIOTOMASI_APIKEY") or ""
MODEL = os.getenv("AIOTOMASI_MODEL") or ""

# ─── Selectable models (frontend picker) ─────────────────────────────────────
# UI label → backend upstream identifier. Hard-coded per product spec; the
# label NEVER hits the upstream API. Unknown values fall back to env MODEL.
SELECTABLE_MODELS = {
    "V-OPUS":   "V-OPUS",
    "V-GEMINI": "V-GEMINI",
    "V-GPT":    "V-GPT",
}
DEFAULT_MODEL_KEY = "V-OPUS"


def _resolve_model(requested):
    """Map a client-supplied model key to an upstream model identifier.

    - None / empty   → falls back to env MODEL (legacy behaviour preserved)
    - Known key      → its mapped value
    - Unknown string → None (caller emits 400)
    """
    if not requested:
        return MODEL or SELECTABLE_MODELS[DEFAULT_MODEL_KEY]
    return SELECTABLE_MODELS.get(requested)

MAX_TOOL_ITERATIONS = 10
MAX_HISTORY_MESSAGES = 12   # cap on prior turns we resend (token saver)

# Heavy guidance is loaded via tools / on demand. The prompt encodes a small
# state machine so the assistant doesn't dump 4 questions at once or rush
# straight to GenerateFullPaper.
SYSTEM_PROMPT = (
    "You are an academic-paper assistant inside PaperFull. "
    "Match the user's language. Keep messages short and warm.\n\n"

    "================  MULTI-STAGE WORKFLOW  ================\n"
    "Treat every paper request as a pipeline: DISCOVERY → SCOPE → "
    "RESEARCH → CONFIRM → GENERATE → REVIEW. Do not skip stages.\n"
    "1. DISCOVERY — figure out the topic, sub-topic, and the user's intent.\n"
    "2. SCOPE     — methodology, dataset/hardware/case, target venue, language.\n"
    "3. RESEARCH  — call SearchPapers (and ReadAttachedFile if files attached) "
    "   to ground the work in real, accessible references.\n"
    "4. CONFIRM   — restate the agreed plan in 4-6 bullets and ask one final "
    "   confirmation before generating.\n"
    "5. GENERATE  — call GenerateFullPaper with a clear prompt. Tell the user "
    "   the editor will load the result automatically (3-10 minutes).\n"
    "6. REVIEW    — after the paper lands, suggest 1-2 specific edits via "
    "   Propose* tools (e.g. tightening abstract, adding a missing citation).\n\n"

    "================  ASK ONE THING AT A TIME  ================\n"
    "Ask ONE question per message. Never dump a 4-bullet list of questions.\n"
    "Each question MUST end with this multi-choice block (3 options + free "
    "input is implicit on the frontend):\n"
    "[OPSI]\n"
    "1) <short option A>\n"
    "2) <short option B>\n"
    "3) <short option C>\n"
    "[/OPSI]\n"
    "Options must be DISTINCT, concrete, and tailored to the user's topic. "
    "Never write generic placeholders like 'option A'. The user can also "
    "type free text — the frontend handles that.\n\n"

    "================  WHEN USER SAYS 'JUST GENERATE IT'  ================\n"
    "If the user says things like 'ngikut aja', 'generate lengkap', "
    "'terserah', 'just go', 'go ahead', 'lanjutkan saja': STOP asking. "
    "Pick reasonable defaults from earlier turns + memory and call "
    "GenerateFullPaper IMMEDIATELY. Do NOT keep emitting ProposeSection one "
    "by one — that is for editing an existing paper, not for first-time "
    "generation. After kicking off the job, write 1-2 sentences telling the "
    "user the job has started and the editor will auto-load the result.\n\n"

    "================  EDITING EXISTING PAPER  ================\n"
    "Only call Propose* tools when a paper already exists and the user wants "
    "to tweak ONE specific part (abstract, a section, a reference, …). "
    "Don't try to assemble a whole paper out of consecutive ProposeSection "
    "calls — use GenerateFullPaper for that.\n\n"

    "================  TOOL HINTS  ================\n"
    "- Keywords always go through ProposeKeywords, never ProposeSection.\n"
    "- ProposeJournal and RequestExportDocx auto-apply.\n"
    "- SearchPapers already filters out broken/inaccessible entries — just "
    "  summarize results, don't re-filter.\n"
    "- Save durable facts via SaveMemory: tentative_title, methodology, "
    "  target_journal, paper_language, dataset, etc.\n\n"

    "When the user asks 'jurnal apa aja' / 'what journals do you support', "
    "list ONLY the templates from '# Available journal templates' below — "
    "do not invent generic options."
)

# Loaded only when the user actually asks for it via the GetGuide tool.
EXTENDED_GUIDE = """# Detailed guide

# When to use each tool
- Title rewrite        → ProposeTitle
- Abstract rewrite     → ProposeAbstract
- Keywords             → ProposeKeywords (replace full list)
- Section              → ProposeSection (section_index=null appends; otherwise replaces)
- Reference            → ProposeReference
- Switch journal       → ProposeJournal (auto-applied)
- Export DOCX          → RequestExportDocx (auto-applied)

# When to save memory
Save things that should persist across all chats of THIS paper:
- Tentative title, target venue, language preference
- Methodology, dataset, metrics
- Tone (formal/IEEE-style/etc)
- Decisions, scope limits

Don't save short-term context.

# Style
Use markdown sparingly. After Propose*, write 1-2 sentences explaining what and why."""


def _gen_id():
    return uuid.uuid4().hex[:16]


def _call_upstream(messages, tools, model=None):
    """Single POST to the upstream chat-completions endpoint. Returns the
    streaming Response on success, or None if the network call itself failed."""
    try:
        return requests.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model or MODEL,
                "messages": messages,
                "stream": True,
                "max_tokens": 32000,
                "thinking": {"type": "adaptive"},
                "tools": tools,
            },
            stream=True,
            timeout=120,
        )
    except requests.RequestException:
        return None


# Cheap keyword router so we only ship the tools the user is plausibly
# going to want this turn — saves a lot of tokens vs sending all of them.
_TOOL_KEYWORDS = {
    "ProposeTitle":      ("title", "judul"),
    "ProposeAbstract":   ("abstract", "abstrak", "ringkasan"),
    "ProposeKeywords":   ("keyword", "kata kunci"),
    "ProposeSection":    ("section", "bagian", "pendahuluan", "introduction",
                          "metodologi", "methodology", "results", "kesimpulan",
                          "conclusion", "diskusi", "discussion", "literatur"),
    "ProposeReference":  ("reference", "referensi", "sitasi", "citation",
                          "daftar pustaka", "bibliography"),
    "ProposeJournal":    ("journal", "jurnal", "template", "ieee", "format"),
    "RequestExportDocx": ("docx", "export", "download", "ekspor", "unduh", "word"),
    "WebSearch":         ("cari ", "search", "google ", "find paper"),
    "WebFetch":          ("buka ", "fetch ", "http://", "https://"),
    "SearchPapers":      ("paper", "literature", "literatur", "slr",
                          "systematic review", "tinjauan pustaka", "referensi terkait",
                          "related work", "state of the art", "sota", "studi pustaka"),
    "GenerateFullPaper": ("buatkan paper", "buatin paper", "buat paper", "generate paper",
                          "tulis paper", "buatkan saya paper", "bikin paper",
                          "tolong buat paper", "lengkapi paper", "draft paper", "full paper"),
    "ListAttachedFiles": ("file terlampir", "file yang saya upload", "lampiran",
                          "attached", "pdf saya", "uploaded"),
    "ReadAttachedFile":  ("baca pdf", "baca file", "isi file", "read pdf", "baca lampiran"),
    "GetPaperContent":   ("lihat paper", "lihat semua", "tampilkan paper"),
    "GetPaperSection":   ("lihat section", "tampilkan section", "section "),
    "Read":              ("baca file project", "buka file", "read "),
    "Bash":              ("ls ", "grep ", "find ", "wc "),
    "SaveMemory":        ("ingat", "remember", "catat", "save", "simpan"),
    "GetMemory":         ("memory", "ingatan"),
    "ListMemory":        ("list memory", "semua memory"),
    "DeleteMemory":      ("hapus memory", "lupakan", "forget"),
}

# Default toolset: small + always-relevant. ListAttachedFiles is cheap and lets
# the model notice user-uploaded references on the very first turn so it can
# ground the discussion in them before generating anything.
_BASE_TOOLS = {"SaveMemory", "GetMemory", "GetPaperContent", "ListAttachedFiles"}


def _select_tools(user_text: str):
    """Return a slim CHAT_TOOLS subset relevant to this turn."""
    needle = (user_text or "").lower()
    selected = set(_BASE_TOOLS)
    for name, kws in _TOOL_KEYWORDS.items():
        if any(kw in needle for kw in kws):
            selected.add(name)
    # If none of the propose-tools matched, still allow ProposeAbstract /
    # ProposeSection because "tulis…" / "write…" are common asks without
    # explicit keywords.
    if any(w in needle for w in ("tulis", "write", "buat", "draft", "rewrite", "perbaiki", "review", "improve", "rapikan")):
        selected.update({"ProposeTitle", "ProposeAbstract", "ProposeSection", "ProposeReference"})
    return [t for t in CHAT_TOOLS if t["name"] in selected]


def _current_user_id():
    raw = get_jwt_identity()
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


# ─── Conversation CRUD ─────────────────────────────────────────────────────

@chat_bp.route('/api/papers/<paper_id>/conversations', methods=['GET'])
@jwt_required()
def list_paper_conversations(paper_id):
    """List all chats inside one paper, newest first."""
    user_id = _current_user_id()
    if user_id is None:
        return {"error": "Unauthorized"}, 401
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return {"error": "Paper not found"}, 404
    convs = (Conversation.query
             .filter_by(user_id=user_id, paper_id=paper_id)
             .order_by(Conversation.updated_at.desc())
             .all())
    return [c.to_dict() for c in convs]


@chat_bp.route('/api/papers/<paper_id>/conversations', methods=['POST'])
@jwt_required()
def create_paper_conversation(paper_id):
    """Create a new chat inside a paper."""
    user_id = _current_user_id()
    if user_id is None:
        return {"error": "Unauthorized"}, 401
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return {"error": "Paper not found"}, 404
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or 'New Chat').strip() or 'New Chat'
    conv = Conversation(
        id=_gen_id(),
        user_id=user_id,
        paper_id=paper_id,
        title=title[:120],
    )
    db.session.add(conv)
    db.session.commit()
    return conv.to_dict(), 201


@chat_bp.route('/api/papers/<paper_id>/conversation', methods=['GET'])
@jwt_required()
def get_or_create_paper_conversation(paper_id):
    """Backwards-compatible: open the most recent chat in a paper, or create one."""
    user_id = _current_user_id()
    if user_id is None:
        return {"error": "Unauthorized"}, 401
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return {"error": "Paper not found"}, 404

    conv = (Conversation.query
            .filter_by(user_id=user_id, paper_id=paper_id)
            .order_by(Conversation.updated_at.desc())
            .first())

    if not conv:
        conv = Conversation(
            id=_gen_id(),
            user_id=user_id,
            paper_id=paper_id,
            title='New Chat',
        )
        db.session.add(conv)
        db.session.commit()

    return conv.to_dict(include_messages=True)


@chat_bp.route('/api/chat/papers', methods=['GET'])
@jwt_required()
def list_paper_chats():
    """One row per paper for the chat sidebar (with chat counts)."""
    user_id = _current_user_id()
    if user_id is None:
        return {"error": "Unauthorized"}, 401
    papers = (Paper.query
              .filter_by(user_id=user_id)
              .order_by(Paper.updated_at.desc())
              .all())
    result = []
    for p in papers:
        convs = (Conversation.query
                 .filter_by(user_id=user_id, paper_id=p.id)
                 .order_by(Conversation.updated_at.desc())
                 .all())
        latest = convs[0] if convs else None
        result.append({
            'paper_id': p.id,
            'title': p.title or 'Untitled Paper',
            'chat_count': len(convs),
            'message_count': sum(len(c.messages) for c in convs),
            'latest_chat_id': latest.id if latest else None,
            'updated_at': (latest.updated_at if latest else p.updated_at).isoformat(),
        })
    return result


@chat_bp.route('/api/chat/conversations/<conv_id>', methods=['GET'])
@jwt_required()
def get_conversation(conv_id):
    user_id = _current_user_id()
    if user_id is None:
        return {"error": "Unauthorized"}, 401
    conv = Conversation.query.filter_by(id=conv_id, user_id=user_id).first()
    if not conv:
        return {"error": "Conversation not found"}, 404
    return conv.to_dict(include_messages=True)


@chat_bp.route('/api/chat/conversations/<conv_id>', methods=['PATCH'])
@jwt_required()
def rename_conversation(conv_id):
    user_id = _current_user_id()
    if user_id is None:
        return {"error": "Unauthorized"}, 401
    conv = Conversation.query.filter_by(id=conv_id, user_id=user_id).first()
    if not conv:
        return {"error": "Conversation not found"}, 404
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    if not title:
        return {"error": "title is required"}, 400
    conv.title = title[:120]
    db.session.commit()
    return conv.to_dict()


@chat_bp.route('/api/chat/conversations/<conv_id>', methods=['DELETE'])
@jwt_required()
def delete_conversation(conv_id):
    user_id = _current_user_id()
    if user_id is None:
        return {"error": "Unauthorized"}, 401
    conv = Conversation.query.filter_by(id=conv_id, user_id=user_id).first()
    if not conv:
        return {"error": "Conversation not found"}, 404
    db.session.delete(conv)
    db.session.commit()
    return {"ok": True}


# ─── Project Memory CRUD (UI access) ──────────────────────────────────────

@chat_bp.route('/api/papers/<paper_id>/memory', methods=['GET'])
@jwt_required()
def list_memory(paper_id):
    user_id = _current_user_id()
    if user_id is None:
        return {"error": "Unauthorized"}, 401
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return {"error": "Paper not found"}, 404
    entries = (ProjectMemory.query
               .filter_by(paper_id=paper_id)
               .order_by(ProjectMemory.updated_at.desc())
               .all())
    return [e.to_dict() for e in entries]


@chat_bp.route('/api/papers/<paper_id>/memory/<int:mem_id>', methods=['DELETE'])
@jwt_required()
def delete_memory_entry(paper_id, mem_id):
    user_id = _current_user_id()
    if user_id is None:
        return {"error": "Unauthorized"}, 401
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return {"error": "Paper not found"}, 404
    entry = ProjectMemory.query.filter_by(id=mem_id, paper_id=paper_id).first()
    if not entry:
        return {"error": "Memory entry not found"}, 404
    db.session.delete(entry)
    db.session.commit()
    return {"ok": True}


# ─── Streaming chat endpoint ───────────────────────────────────────────────

@chat_bp.route('/api/chat/conversations/<conv_id>/messages', methods=['POST'])
@jwt_required()
def send_message(conv_id):
    user_id = _current_user_id()
    if user_id is None:
        return {"error": "Unauthorized"}, 401
    conv = Conversation.query.filter_by(id=conv_id, user_id=user_id).first()
    if not conv:
        return {"error": "Conversation not found"}, 404

    data = request.get_json(silent=True) or {}
    content = (data.get('content') or '').strip()
    if not content:
        return {"error": "Message content is required"}, 400
    if len(content) > 16000:
        return {"error": "Message is too long (max 16000 chars)"}, 400

    requested_model = (data.get('model') or '').strip() or None
    upstream_model = _resolve_model(requested_model)
    if upstream_model is None:
        return {"error": f"Unknown model. Allowed: {sorted(SELECTABLE_MODELS.keys())}"}, 400
    log.info("chat.send conv=%s user=%s model=%s len=%d", conv_id, user_id, upstream_model, len(content))

    user_msg = ChatMessage(
        conversation_id=conv_id,
        role='user',
        content=content
    )
    db.session.add(user_msg)

    # Auto-title from first user message if still default
    if conv.title in (None, '', 'New Chat'):
        conv.title = (content[:60] + ('…' if len(content) > 60 else '')) or 'New Chat'
    db.session.commit()

    def generate():
        try:
            messages = _build_messages(conv)
            selected_tools = _select_tools(content)
            assistant_content = ""
            assistant_thinking = ""
            all_tool_calls_data = []

            for iteration in range(MAX_TOOL_ITERATIONS):
                tool_calls_raw = []
                chunk_content = ""
                chunk_thinking = ""

                response = _call_upstream(messages, selected_tools, model=upstream_model)

                if response is None or response.status_code != 200:
                    code = response.status_code if response is not None else 'no-response'
                    # One retry without tools — large tool outputs are the
                    # most common cause of upstream 500s. Without tools the
                    # model can still produce a useful text reply.
                    if code == 500 and selected_tools:
                        yield _sse("text", {"content": (
                            "\n\n_(Upstream API hiccup — mencoba lagi tanpa tool…)_\n\n"
                        )})
                        retry = _call_upstream(messages, [], model=upstream_model)
                        if retry is not None and retry.status_code == 200:
                            response = retry
                        else:
                            yield _sse("error", {"message": (
                                f"API error: {code}. Coba pesan lebih pendek atau "
                                "buat chat baru kalau berulang."
                            )})
                            return
                    else:
                        yield _sse("error", {"message": f"API error: {code}"})
                        return

                for line in response.iter_lines():
                    if not line:
                        continue
                    line = line.decode("utf-8")
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break

                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    choices = chunk.get("choices", [])
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {})

                    if "content" in delta and delta["content"]:
                        text = delta["content"]
                        chunk_content += text
                        yield _sse("text", {"content": text})

                    if "thinking" in delta and delta["thinking"]:
                        thinking = delta["thinking"]
                        if isinstance(thinking, dict) and "content" in thinking:
                            t = thinking["content"]
                        elif isinstance(thinking, str):
                            t = thinking
                        else:
                            t = ""
                        if t:
                            chunk_thinking += t
                            yield _sse("thinking", {"content": t})

                    if "tool_calls" in delta:
                        for tc in delta["tool_calls"]:
                            idx = tc.get("index", 0)
                            while len(tool_calls_raw) <= idx:
                                tool_calls_raw.append({"id": "", "name": "", "arguments": ""})
                            if "id" in tc:
                                tool_calls_raw[idx]["id"] = tc["id"]
                            if "function" in tc:
                                if "name" in tc["function"]:
                                    tool_calls_raw[idx]["name"] = tc["function"]["name"]
                                if "arguments" in tc["function"]:
                                    tool_calls_raw[idx]["arguments"] += tc["function"]["arguments"]

                assistant_content += chunk_content
                assistant_thinking += chunk_thinking

                if not tool_calls_raw:
                    break

                # Stamp every tool_call with a stable id BEFORE we use it twice
                # (once on the assistant message, once on the tool message). Re-
                # generating the id on the tool side caused a mismatch and a 500.
                for tc in tool_calls_raw:
                    if not tc.get("id"):
                        tc["id"] = f"call_{_gen_id()}"

                messages.append({
                    "role": "assistant",
                    "content": chunk_content if chunk_content else None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": tc["arguments"]
                            }
                        }
                        for tc in tool_calls_raw
                    ]
                })

                for tc in tool_calls_raw:
                    tool_name = tc["name"]
                    try:
                        args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                    except json.JSONDecodeError:
                        args = {}

                    yield _sse("tool_call", {"name": tool_name, "arguments": args})

                    result = execute_tool(tool_name, args, user_id, conv.paper_id)

                    # Forward the raw result to the frontend so it can route
                    # proposals through the diff/apply flow.
                    yield _sse("tool_result", {"name": tool_name, "result": result[:2000]})

                    # But scrub the internal proposal sentinel before re-feeding
                    # the result back to the model. Otherwise the model sees the
                    # JSON payload and gets confused, sometimes triggering 500s.
                    upstream_result = result
                    if isinstance(result, str) and result.startswith("<<PROPOSAL>>"):
                        if tool_name == "ProposeJournal":
                            upstream_result = (
                                f"Journal switched to {args.get('journal','')} (auto-applied)."
                            )
                        elif tool_name == "RequestExportDocx":
                            upstream_result = "DOCX export triggered (auto-applied)."
                        elif tool_name == "GenerateFullPaper":
                            try:
                                payload = json.loads(result[len("<<PROPOSAL>>"):])
                                upstream_result = (
                                    f"Full-paper generation job started (job_id="
                                    f"{payload.get('job_id','?')}). The user's editor will "
                                    f"poll and load the result automatically. Tell the user to "
                                    f"wait 3–10 minutes and continue chatting in the meantime."
                                )
                            except Exception:
                                upstream_result = "Full-paper generation job started."
                        else:
                            upstream_result = (
                                f"Proposal recorded. The user will review and accept/reject "
                                f"in the Preview tab."
                            )

                    all_tool_calls_data.append({
                        "name": tool_name,
                        "arguments": args,
                        "result": result[:2000]
                    })

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": upstream_result
                    })

            assistant_msg = ChatMessage(
                conversation_id=conv_id,
                role='assistant',
                content=assistant_content,
                thinking=assistant_thinking if assistant_thinking else None,
                tool_calls=all_tool_calls_data if all_tool_calls_data else None
            )
            db.session.add(assistant_msg)
            db.session.commit()

            yield _sse("done", {"message_id": assistant_msg.id})

        except Exception as e:
            yield _sse("error", {"message": str(e)})

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        }
    )


def _list_available_journals():
    """Return list of available journal template codes (matches /api/journals)."""
    try:
        from pathlib import Path
        template_dir = Path(__file__).parent / "template"
        codes = []
        for docx_path in template_dir.glob("*.docx"):
            code = docx_path.stem
            if (template_dir / f"{code}gen.py").exists():
                codes.append(code)
        return sorted(set(codes), key=str.lower)
    except Exception:
        return []


def _build_messages(conv):
    messages = []

    db_messages = ChatMessage.query.filter_by(
        conversation_id=conv.id
    ).order_by(ChatMessage.created_at).all()
    is_first_turn = len([m for m in db_messages if m.role == 'assistant']) == 0

    system_content = SYSTEM_PROMPT
    if conv.paper_id:
        # Only inject the paper meta on the FIRST turn — afterwards the
        # model can call GetPaperContent on demand. Saves tokens every reply.
        if is_first_turn:
            paper = Paper.query.get(conv.paper_id)
            if paper:
                paper_meta = {"title": paper.title, "id": paper.id}
                if paper.data:
                    data = dict(paper.data)
                    for k in ("sections", "references", "figures", "tables", "equations"):
                        if isinstance(data.get(k), list) and len(data[k]) > 0:
                            data[k] = data[k][:6]
                    paper_meta.update({
                        "abstract": (data.get("abstract") or "")[:300],
                        "keywords": data.get("keywords") or [],
                        "section_titles": [s.get("title") for s in (data.get("sections") or []) if s.get("title")],
                    })
                system_content += f"\n\n# Paper\n{json.dumps(paper_meta, ensure_ascii=False)[:1200]}"

            # First-turn: also tell the model exactly which journal templates
            # are installed so it answers the user's "what journals do you
            # support?" question with the real list, not a generic answer.
            journals = _list_available_journals()
            if journals:
                system_content += "\n\n# Available journal templates (real, installed): " + ", ".join(journals)

        memory_summary = get_memory_summary(conv.paper_id)
        if memory_summary:
            system_content += f"\n\n# Memory\n{memory_summary[:1500]}"

    messages.append({"role": "system", "content": system_content})

    # Cap history to last MAX_HISTORY_MESSAGES turns to keep context bounded.
    trimmed = db_messages[-MAX_HISTORY_MESSAGES:] if len(db_messages) > MAX_HISTORY_MESSAGES else db_messages
    for msg in trimmed:
        messages.append({
            "role": msg.role if msg.role in ("user", "assistant") else "user",
            "content": msg.content
        })

    return messages


def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
