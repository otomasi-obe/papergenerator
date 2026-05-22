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
import re
import threading
import time
import uuid
import datetime
import requests
from flask import Blueprint, request, Response, stream_with_context
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import db, Conversation, ChatMessage, Paper, ProjectMemory, User
from chat_tools import execute_tool, CHAT_TOOLS, get_memory_summary
try:
    from chat_tools import _log_chat_call  # type: ignore
except ImportError:
    def _log_chat_call(*_args, **_kwargs):  # noqa: D401 — placeholder
        """No-op when chat_tools._log_chat_call hasn't landed yet (Agent 2)."""
        return None
from mode_prompts import get_mode_bundle, list_modes
from auto_memory import extract_facts
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)
chat_bp = Blueprint('chat', __name__)

_AIOTOMASI_API_BASE = os.getenv("AIOTOMASI_API") or ""
API_URL = (_AIOTOMASI_API_BASE.rstrip('/') + "/chat/completions") if _AIOTOMASI_API_BASE else ""
API_KEY = os.getenv("AIOTOMASI_APIKEY") or ""
MODEL = os.getenv("AIOTOMASI_MODEL") or ""

# ─── Hard-coded chat model ────────────────────────────────────────────────
# Chat is always served by V-DEEPSEEK. The frontend may still send a `model`
# field on the request body; it is ignored silently for back-compat.
CHAT_MODEL = "V-DEEPSEEK"

MAX_TOOL_ITERATIONS = 10
MAX_HISTORY_MESSAGES = 12   # cap on prior turns we resend (token saver)

# Mode storage. The Conversation model has no JSON metadata column today,
# so per-conversation mode is kept in an in-memory dict keyed by conv.id.
# Resetting on backend restart is acceptable: tier-0 RouteIntent re-classifies
# on the very next user turn, so the worst case is one extra router call.
_CONV_MODE: dict[str, str] = {}
_CONV_MODE_LOCK = threading.Lock()

# Heuristic for "show me what you remember" so we keep memory injection cheap.
_MEMORY_RECALL_RE = re.compile(
    r"(?i)(ingatan|memori|memory|apa.*kamu.*tau|apa.*kamu.*ingat)"
)

# Heavy guidance now lives in mode_prompts.py. Each mode (tier0/discovery/
# slr/edit/rapikan/memory/casual) ships a slim system prompt + scoped tool
# list selected by the tier-0 RouteIntent classifier on first turn.


def _gen_id():
    return uuid.uuid4().hex[:16]


# ── Error sanitization ───────────────────────────────────────────────────────
# We never echo SQL fragments, stack traces, or vendor exception class names
# to the chat UI — that's both confusing for users and a small information leak.
# The full traceback still lands in app.log via log.exception(...).
_SQL_HINT_RE = re.compile(
    r"psycopg2|sqlalchemy|UndefinedTable|relation\s+\".*\"\s+does\s+not\s+exist|"
    r"IntegrityError|OperationalError|ProgrammingError",
    re.IGNORECASE,
)
_TRACEBACK_HINT_RE = re.compile(
    r"Traceback|File\s+\".*\",\s+line\s+\d+|raise\s+[A-Za-z]+Error",
    re.IGNORECASE,
)


def _safe_user_error(raw: object, fallback: str = "Terjadi kendala teknis. Coba kirim lagi sebentar.") -> str:
    s = ("" if raw is None else str(raw)).strip()
    if not s:
        return fallback
    if _SQL_HINT_RE.search(s) or _TRACEBACK_HINT_RE.search(s):
        return "Ada gangguan internal di server. Coba kirim lagi sebentar."
    if s.lower().startswith("api error:") or "upstream" in s.lower():
        return "AI sedang sibuk. Coba kirim lagi sebentar."
    if len(s) > 240:
        return s[:240] + "…"
    return s


# ── Per-turn JSON log ────────────────────────────────────────────────────────
# Layout: backend/log/<user_slug>/<paper_id>/<chat_id>/<turn-id>.send.json
#         backend/log/<user_slug>/<paper_id>/<chat_id>/<turn-id>.recv.json
# Used for after-the-fact debugging of an individual chat turn (request payload
# the AI saw + the assistant turn it produced). All errors here are swallowed
# — logging must NEVER crash a chat stream.
_TURN_LOG_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "log")
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_path_seg(value: object, fallback: str) -> str:
    s = _SAFE_NAME_RE.sub("_", str(value or "")).strip("._-")
    return s or fallback


def _user_dir_slug(user_id) -> str:
    """Map `user_id` to a directory-safe identifier ('<id>__<email-local>').

    Falls back to '<id>' if the user is not findable / has no email.
    """
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return _safe_path_seg(user_id, "anon")
    user = User.query.get(uid)
    if user and user.email:
        local = user.email.split("@", 1)[0]
        return f"{uid}__{_safe_path_seg(local, 'user')}"
    return f"{uid}"


def _turn_log_dir(user_id, paper_id, chat_id) -> str | None:
    try:
        u = _user_dir_slug(user_id)
        p = _safe_path_seg(paper_id, "_no-paper")
        c = _safe_path_seg(chat_id, "_no-chat")
        path = os.path.join(_TURN_LOG_ROOT, u, p, c)
        os.makedirs(path, exist_ok=True)
        return path
    except Exception as e:
        log.warning("turn_log_dir failed: %s", e)
        return None


def _write_turn_log(dirpath: str | None, turn_id: str, kind: str, payload: dict) -> None:
    if not dirpath or not turn_id:
        return
    try:
        fname = os.path.join(dirpath, f"{turn_id}.{kind}.json")
        body = {
            "ts": datetime.datetime.utcnow().isoformat() + "Z",
            "kind": kind,
            **payload,
        }
        with open(fname, "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning("write_turn_log failed (%s): %s", kind, e)


# ── Upstream concurrency control ────────────────────────────────────────────
# Global semaphore caps how many upstream requests we hold open per worker
# process. Without this, when several users (or several papers in the same
# user's tabs) hit /chat at once, all gthread threads block on the upstream
# socket and ApiGW returns 500/429. Cap chosen so 4 workers × 8 threads can
# still serve cheap endpoints (quota, list_papers) while a few heavy chat
# streams are in flight.
_MAX_UPSTREAM_INFLIGHT = int(os.getenv("CHAT_UPSTREAM_INFLIGHT", "3"))
_upstream_sem = threading.BoundedSemaphore(_MAX_UPSTREAM_INFLIGHT)


def _call_upstream(messages, tools, model="V-DEEPSEEK", _allow_no_thinking=True):
    """POST to the upstream chat-completions endpoint with retry/backoff.

    Hard-coded model: V-DEEPSEEK for all chat. No fallback chain.

    Returns the streaming Response on success (status 200), or None on
    network failure / persistent error. The caller is responsible for
    reading the stream and surfacing an SSE error if the return is None.

    Retry policy:
      - 429 / 5xx        → up to 3 attempts with exponential backoff (0.8s, 1.6s, 3.2s)
      - 400 + thinking   → one retry without thinking (some payloads/tool combos
                           confuse adaptive thinking on the upstream side)
      - persistent error → return None (caller emits SSE error)
    """
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    base_payload = {
        "messages": messages,
        "stream": True,
        "max_tokens": 32000,
        "thinking": {"type": "adaptive"},
        "tools": tools,
        "model": model,
    }

    if not _upstream_sem.acquire(timeout=90):
        log.warning("_call_upstream: semaphore acquire timeout")
        return None

    try:
        last = None
        for attempt in range(3):
            try:
                resp = requests.post(
                    API_URL, headers=headers, json=base_payload,
                    stream=True, timeout=180,
                )
            except requests.RequestException as e:
                log.warning("_call_upstream net err attempt=%d: %s", attempt, e)
                last = None
                time.sleep(0.8 * (2 ** attempt))
                continue

            if resp.status_code == 200:
                return resp

            # 400 + thinking → drop thinking and retry once.
            if (resp.status_code == 400 and _allow_no_thinking
                    and base_payload.get("thinking")):
                resp.close()
                base_payload.pop("thinking", None)
                try:
                    resp2 = requests.post(
                        API_URL, headers=headers, json=base_payload,
                        stream=True, timeout=180,
                    )
                    if resp2.status_code == 200:
                        return resp2
                    last = resp2
                except requests.RequestException as e:
                    log.warning("_call_upstream no-think err: %s", e)
                    last = None

            # 429 or 5xx → backoff and retry.
            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                last = resp
                try:
                    body = resp.raw.read(200, decode_content=True)
                    log.warning("_call_upstream %s attempt=%d body=%r",
                                resp.status_code, attempt, body[:200])
                except Exception:
                    pass
                resp.close()
                if attempt < 2:
                    time.sleep(0.8 * (2 ** attempt))
                    continue

            # Other 4xx → return so caller emits a useful error.
            return resp

        return last
    finally:
        _upstream_sem.release()


# ─── Active-generation registry ───────────────────────────────────────────
# In-memory map: paper_id -> AiJob.id of an active GenerateFullPaper job.
# Set from chat_tools._generate_full_paper via register_active_job(); cleared
# on completion or when send_message detects a stale entry.
_active_jobs_by_paper: dict[str, str] = {}
_active_jobs_lock = threading.Lock()


def register_active_job(paper_id: str | None, job_id: str) -> None:
    """Record that `job_id` is the active generation job for `paper_id`.
    Called by chat_tools._generate_full_paper right after kicking off the
    background thread. Safe to call with a None paper_id (no-op)."""
    if not paper_id or not job_id:
        return
    with _active_jobs_lock:
        _active_jobs_by_paper[paper_id] = job_id


def clear_active_job(paper_id: str | None) -> None:
    """Forget the active job for a paper. Called by chat_tools when the
    job-runner thread observes a terminal status, or by send_message when
    it spots a stale entry pointing at a non-pending job."""
    if not paper_id:
        return
    with _active_jobs_lock:
        _active_jobs_by_paper.pop(paper_id, None)


# ─── Mode helpers ─────────────────────────────────────────────────────────

def _resolve_mode(conv) -> str:
    """Read the conversation's current mode. Defaults to 'tier0'."""
    if conv is None or not getattr(conv, "id", None):
        return "tier0"
    with _CONV_MODE_LOCK:
        return _CONV_MODE.get(conv.id) or "tier0"


def _set_mode(conv, mode: str) -> None:
    """Persist the conversation's mode (process-local, see _CONV_MODE)."""
    if conv is None or not getattr(conv, "id", None) or not mode:
        return
    with _CONV_MODE_LOCK:
        _CONV_MODE[conv.id] = mode


def _get_last_assistant_msg(conv_id: str) -> str | None:
    msg = (ChatMessage.query
           .filter_by(conversation_id=conv_id, role="assistant")
           .order_by(ChatMessage.created_at.desc())
           .first())
    return msg.content if msg else None


def _find_tool_by_name(name: str):
    """Look up a tool schema in CHAT_TOOLS by its declared name."""
    if not name:
        return None
    for t in CHAT_TOOLS:
        # Anthropic-style schemas use a top-level "name"; OpenAI-style nest
        # the name under function. Support both so this stays correct as
        # CHAT_TOOLS evolves.
        if t.get("name") == name:
            return t
        fn = t.get("function") or {}
        if fn.get("name") == name:
            return t
    return None


def _select_tools(conv, content: str):
    """Return ``(system_prompt, tool_schemas)`` for this turn based on mode."""
    mode = _resolve_mode(conv)
    sysprompt, tool_names = get_mode_bundle(mode)
    tools = []
    for name in tool_names:
        schema = _find_tool_by_name(name)
        if schema is not None:
            tools.append(schema)
    return sysprompt, tools


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

    # Frontend may still send a `model` field; ignore silently for back-compat.
    # All chat is hard-coded to CHAT_MODEL.
    log.info("chat.send conv=%s user=%s model=%s len=%d", conv_id, user_id, CHAT_MODEL, len(content))

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

    # Auto-extract durable facts from the user's reply (jurusan, topik, …).
    # Runs synchronously but is internally guarded so any failure here cannot
    # break the chat stream.
    try:
        last_a = _get_last_assistant_msg(conv.id)
        extract_facts(conv.paper_id, user_id, conv, content, last_assistant_msg=last_a)
    except Exception as e:
        log.exception("auto_memory.extract_facts failed: %s", e)

    # Per-call JSONL log: user turn.
    try:
        _log_chat_call(conv.paper_id, conv.id, "user", {"content": content[:2000]})
    except Exception:
        log.exception("_log_chat_call user failed")

    # Per-turn structured log (one JSON per request + one per response). Lets
    # us trace any failed turn end-to-end without grepping logs.
    turn_id = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S") + "_" + _gen_id()
    turn_dir = _turn_log_dir(user_id, conv.paper_id, conv.id)
    _write_turn_log(turn_dir, turn_id, "send", {
        "user_id": user_id,
        "paper_id": conv.paper_id,
        "conv_id": conv.id,
        "model": CHAT_MODEL,
        "content": content[:8000],
        "len": len(content),
    })

    def generate():
        try:
            sysprompt, selected_tools = _select_tools(conv, content)
            messages = _build_messages(conv, sysprompt, content)
            assistant_content = ""
            assistant_thinking = ""
            all_tool_calls_data = []
            total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

            for iteration in range(MAX_TOOL_ITERATIONS):
                tool_calls_raw = []
                chunk_content = ""
                chunk_thinking = ""
                mode_changed = False  # Set if a RouteIntent tool fires this iter

                response = _call_upstream(messages, selected_tools, model=CHAT_MODEL)

                if response is None or response.status_code != 200:
                    code = response.status_code if response is not None else 'no-response'
                    # One retry without tools — large tool outputs are the
                    # most common cause of upstream 500s. Without tools the
                    # model can still produce a useful text reply.
                    if code == 500 and selected_tools:
                        yield _sse("text", {"content": (
                            "\n\n_(Sambungan ke AI sedang macet — mencoba lagi…)_\n\n"
                        )})
                        retry = _call_upstream(messages, [], model=CHAT_MODEL)
                        if retry is not None and retry.status_code == 200:
                            response = retry
                        else:
                            log.warning("chat upstream retry failed: code=%s", code)
                            yield _sse("error", {"message": (
                                "AI sedang sibuk. Coba kirim lagi sebentar, atau "
                                "buat chat baru kalau berulang."
                            )})
                            return
                    else:
                        log.warning("chat upstream failed: code=%s", code)
                        yield _sse("error", {"message": "AI sedang sibuk. Coba kirim lagi sebentar."})
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
                        # Some upstreams emit a final no-choices chunk that
                        # carries the usage block. Capture it for token logging.
                        if "usage" in chunk and chunk["usage"]:
                            u = chunk["usage"]
                            try:
                                total_usage["prompt_tokens"] += int(u.get("prompt_tokens", 0) or 0)
                                total_usage["completion_tokens"] += int(u.get("completion_tokens", 0) or 0)
                                total_usage["total_tokens"] += int(u.get("total_tokens", 0) or 0)
                            except (TypeError, ValueError):
                                pass
                        continue
                    delta = choices[0].get("delta", {})

                    # Some streams attach usage to the last choice-bearing
                    # chunk too. Read it whenever it shows up.
                    if "usage" in chunk and chunk["usage"]:
                        u = chunk["usage"]
                        try:
                            total_usage["prompt_tokens"] += int(u.get("prompt_tokens", 0) or 0)
                            total_usage["completion_tokens"] += int(u.get("completion_tokens", 0) or 0)
                            total_usage["total_tokens"] += int(u.get("total_tokens", 0) or 0)
                        except (TypeError, ValueError):
                            pass

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

                    # Log tool call for debugging Bug A
                    log.info(f"[TOOL_CALL] AI requested tool: {tool_name} with args: {json.dumps(args, ensure_ascii=False)[:500]}")

                    yield _sse("tool_call", {"name": tool_name, "arguments": args})

                    # ── RouteIntent — mode router ───────────────────────
                    # Tier-0 classifier. We don't feed the result back as a
                    # tool-result message; instead we switch the active mode
                    # bundle and re-call upstream so the model continues with
                    # the right system prompt + tool subset.
                    if tool_name == "RouteIntent":
                        new_mode = (args.get("mode") or "").strip().lower()
                        if new_mode in list_modes() and new_mode != _resolve_mode(conv):
                            _set_mode(conv, new_mode)
                            mode_changed = True
                            log.info(
                                "chat.route conv=%s mode=%s reason=%s",
                                conv.id, new_mode, args.get("reasoning", "")[:120],
                            )
                        # Surface the route to the frontend (no proposal panel).
                        yield _sse("tool_result", {
                            "name": tool_name,
                            "result": json.dumps({"mode": new_mode}, ensure_ascii=False),
                        })
                        all_tool_calls_data.append({
                            "name": tool_name, "arguments": args,
                            "result": f"routed -> {new_mode}",
                        })
                        # Don't append a tool message — we'll rebuild messages
                        # after this iteration with the new mode bundle.
                        continue

                    try:
                        result = execute_tool(tool_name, args, user_id, conv.paper_id, conv_id=conv.id)
                        log.info(f"[TOOL_RESULT] {tool_name} returned: {str(result)[:500]}")
                    except Exception as e:
                        log.error(f"[TOOL_ERROR] {tool_name} failed: {type(e).__name__}: {str(e)}", exc_info=True)
                        # Friendly message for the user; full detail stays in logs.
                        friendly = _safe_user_error(
                            f"{tool_name} gagal: {e}",
                            fallback=f"Tool {tool_name} sedang bermasalah. Coba lagi sebentar."
                        )
                        yield _sse("tool_result", {"name": tool_name, "result": friendly})
                        yield _sse("error", {"message": friendly})
                        return

                    # ── ProposeChips — UI hint ──────────────────────────
                    # Surface as a typed SSE event so the frontend renders
                    # clickable chip buttons next to the assistant message.
                    if tool_name == "ProposeChips" and isinstance(result, str) and result.startswith("<<PROPOSAL>>"):
                        try:
                            chip_payload = json.loads(result[len("<<PROPOSAL>>"):])
                            yield _sse("chips", {
                                "chips": chip_payload.get("chips") or [],
                                "context_hint": chip_payload.get("context_hint", ""),
                            })
                        except Exception:
                            pass

                    # Surface tool-side error strings (validation/setup failures)
                    # so the user sees them as a real error, not a hallucinated
                    # success message. Applies to mutation/job tools only.
                    if (isinstance(result, str)
                            and result.startswith("Error:")
                            and tool_name in {"GenerateFullPaper", "RunSLR"}):
                        log.warning(f"[TOOL_VALIDATION_ERROR] {tool_name}: {result[:500]}")
                        yield _sse("tool_result", {"name": tool_name, "result": result[:2000]})
                        yield _sse("error", {"message": result})
                        return

                    # Forward the raw result to the frontend so it can route
                    # proposals through the diff/apply flow.
                    yield _sse("tool_result", {"name": tool_name, "result": result[:2000]})

                    # Emit a typed open_tab event for RunSLR so the frontend
                    # has a canonical signal (no parsing of the result string).
                    if tool_name == "RunSLR" and isinstance(result, str) and result.startswith("<<PROPOSAL>>"):
                        try:
                            _payload = json.loads(result[len("<<PROPOSAL>>"):])
                            yield _sse("open_tab", {
                                "tab": "literature",
                                "reason": "slr_started",
                                "job_id": _payload.get("job_id"),
                                "query":  _payload.get("query"),
                                "top_k":  _payload.get("top_k", 50),
                                "ai_model": _payload.get("ai_model", "V-DEEPSEEK"),
                            })
                        except Exception:
                            pass

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
                        elif tool_name == "RunSLR":
                            try:
                                payload = json.loads(result[len("<<PROPOSAL>>"):])
                                upstream_result = (
                                    f"SLR job queued (job_id={payload.get('job_id','?')}, "
                                    f"query={payload.get('query','')!r}, "
                                    f"top_k={payload.get('top_k', 50)}, ai={payload.get('ai_model','V-DEEPSEEK')}). "
                                    f"The Literature tab will populate automatically once "
                                    f"the worker finishes (~2-5 menit). Tell the user to "
                                    f"watch the Literatur tab; meanwhile they can keep "
                                    f"chatting. Don't repeat the long results — let the "
                                    f"frontend render them."
                                )
                            except Exception:
                                upstream_result = "SLR job queued."
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

                # If the model just routed to a new mode, rebuild messages
                # with the new mode bundle and continue the iteration loop.
                # The model now has the mode-specific prompt + tool subset.
                if mode_changed:
                    sysprompt, selected_tools = _select_tools(conv, content)
                    messages = _build_messages(conv, sysprompt, content)

            assistant_msg = ChatMessage(
                conversation_id=conv_id,
                role='assistant',
                content=assistant_content,
                thinking=assistant_thinking if assistant_thinking else None,
                tool_calls=all_tool_calls_data if all_tool_calls_data else None
            )
            # Per-call JSONL log: assistant turn.
            try:
                _log_chat_call(conv.paper_id, conv.id, "assistant", {
                    "content": assistant_content[:4000],
                    "tool_calls": all_tool_calls_data,
                    "usage": total_usage,
                })
            except Exception:
                log.exception("_log_chat_call assistant failed")
            # Per-turn structured log: assistant final.
            _write_turn_log(turn_dir, turn_id, "recv", {
                "user_id": user_id,
                "paper_id": conv.paper_id,
                "conv_id": conv.id,
                "model": CHAT_MODEL,
                "content": assistant_content[:16000],
                "thinking": (assistant_thinking or "")[:8000] or None,
                "tool_calls": all_tool_calls_data,
                "usage": total_usage,
                "status": "ok",
            })
            db.session.add(assistant_msg)
            db.session.commit()

            # Token quota accounting — fire-and-forget so streaming response
            # isn't held up by the bookkeeping write.
            try:
                if total_usage["total_tokens"] > 0:
                    from app import _log_api_usage
                    threading.Thread(
                        target=_log_api_usage,
                        args=("chat", total_usage, user_id),
                        daemon=True,
                    ).start()
            except Exception:
                pass

            yield _sse("done", {"message_id": assistant_msg.id})

        except Exception as e:
            log.exception("chat stream failed")
            try:
                _write_turn_log(turn_dir, turn_id, "recv", {
                    "user_id": user_id,
                    "paper_id": conv.paper_id,
                    "conv_id": conv.id,
                    "model": CHAT_MODEL,
                    "status": "error",
                    "error_class": type(e).__name__,
                    "error": str(e)[:4000],
                })
            except Exception:
                pass
            yield _sse("error", {"message": _safe_user_error(e)})

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


def _build_messages(conv, system_content: str, user_content: str = ""):
    """Assemble the messages list for upstream.

    ``system_content`` is the mode-specific prompt from ``_select_tools``;
    paper meta (first turn only), journal templates (first turn only) and
    project memory (first turn or memory-recall asks) are appended on top.
    """
    messages = []

    db_messages = ChatMessage.query.filter_by(
        conversation_id=conv.id
    ).order_by(ChatMessage.created_at).all()
    is_first_turn = len([m for m in db_messages if m.role == 'assistant']) == 0

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

        # Memory injection is gated: heavy on first turn (so the model knows
        # what the user already locked in) or when the user explicitly asks
        # about memory. Otherwise auto-extracted facts already live in their
        # own ProjectMemory rows and the model can call ListMemory on demand.
        if is_first_turn or (user_content and _MEMORY_RECALL_RE.search(user_content)):
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
