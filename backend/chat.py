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
import threading
import time
import uuid
import requests
from flask import Blueprint, request, Response, stream_with_context
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import db, Conversation, ChatMessage, Paper, ProjectMemory, AiJob
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
    "V-OPUS":     "V-OPUS",
    "V-CLAUDE":   "V-CLAUDE",
    "V-GPT":      "V-GPT",
    "V-GLM":      "V-GLM",
    "V-DEEPSEEK": "V-DEEPSEEK",
}
DEFAULT_MODEL_KEY = "V-CLAUDE"


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
    "You are PaperFull's academic-paper assistant. "
    "Match the user's language (Bahasa Indonesia by default). "
    "Keep messages short, warm, and concrete.\n\n"

    "================  7-STEP DISCOVERY WORKFLOW  ================\n"
    "Before generating ANY paper, you MUST walk the user through these 7 "
    "steps IN ORDER, ONE QUESTION PER MESSAGE. After each user reply, save "
    "the answer with SaveMemory using the exact `key` shown in brackets, "
    "then move to the next step. Skip ahead only if the user already "
    "answered that step in an earlier turn (check GetMemory first).\n\n"

    "STEP 1 — JURUSAN [key=jurusan]\n"
    "  Ask the user's field/jurusan (e.g. Teknik Elektro, Manajemen, Hukum, "
    "  Kedokteran). Tailor option 1/2/3 to common jurusan.\n\n"

    "STEP 2 — TOPIK [key=topik]\n"
    "  Ask the specific topic within their jurusan. Options must be 3 "
    "  realistic topic ideas inside their jurusan.\n\n"

    "STEP 3 — LATAR BELAKANG [key=latar_belakang]\n"
    "  Ask WHY this topic matters to them — the motivation/problem. "
    "  Options should be 3 plausible motivations for that topik.\n\n"

    "STEP 4 — LITERATUR REVIEW [key=referensi_terpilih]\n"
    "  Ask whether the user already has literature, or wants help finding "
    "  it. Options: 1) Belum, tolong carikan  2) Sudah, ini filenya  "
    "  3) Pakai keduanya.\n"
    "  - If 'belum / cari': call SearchPapers with the topic, then "
    "    summarize the 8-12 best results in a short bullet list. Ask "
    "    'pakai semua atau ada yang mau diganti?'. After the user "
    "    confirms, SaveMemory(key=referensi_terpilih, value=<short list "
    "    of titles>).\n"
    "  - If 'sudah, file terlampir': call ListAttachedFiles. For EACH "
    "    file returned (not just one), call ReadAttachedFile and write a "
    "    2-sentence summary per file. If a file has extracted_chars=0, "
    "    tell the user: 'file ini tidak bisa diekstrak, coba upload ulang "
    "    dalam format text-based PDF'. Make sure at least 1 file is "
    "    readable before continuing.\n\n"

    "STEP 5 — METODE [key=metode]\n"
    "  Suggest 3 concrete methodologies that fit the jurusan + topik + "
    "  literature. Discuss in depth — if the user is unsure, keep "
    "  discussing rather than locking in. Save only after the user "
    "  confirms.\n\n"

    "STEP 6 — DATA [key=data_asli OR key=data_estimasi]\n"
    "  Ask whether they have real data or only estimates. Options: "
    "  1) Punya data riil  2) Estimasi saja  3) Campuran.\n"
    "  - 'punya data': accept their text description of the dataset, "
    "    SaveMemory(key=data_asli).\n"
    "  - 'estimasi': propose a realistic synthetic dataset given their "
    "    metode (e.g. 'untuk eksperimen IoT, 30 hari pengukuran tiap 5 "
    "    menit = 8640 data point per sensor'), SaveMemory(key="
    "    data_estimasi).\n\n"

    "STEP 7 — KESIMPULAN TARGET [key=kesimpulan_target]\n"
    "  Ask what outcome / conclusion they hope the paper produces. "
    "  Options: 3 plausible outcomes for that topic+metode.\n\n"

    "STEP 8 — CONFIRM (no question — just summary):\n"
    "  Restate all 7 answers as 7 short bullets, then close with this "
    "  exact options block:\n"
    "  [OPSI]\n"
    "  1) Sudah pas, generate sekarang\n"
    "  2) Tambah/revisi <field>\n"
    "  3) Ubah <field>\n"
    "  [/OPSI]\n\n"

    "STEP 9 — GENERATE:\n"
    "  Once the user confirms, call GenerateFullPaper(prompt=<topik>). "
    "  Do NOT ask anything else. After the call, send 1-2 sentences: "
    "  'Job dimulai. Editor akan auto-load hasilnya 3-10 menit. Kamu "
    "  bisa pakai chat lain untuk hal lain (kecuali generate paper "
    "  untuk paper yang sama).'\n\n"

    "================  ASK ONE THING AT A TIME  ================\n"
    "Ask exactly ONE question per message. Never dump multiple questions. "
    "EVERY question MUST end with this exact block:\n"
    "[OPSI]\n"
    "1) <concrete option tailored to the topic>\n"
    "2) <different concrete option>\n"
    "3) <third concrete option>\n"
    "[/OPSI]\n"
    "Options must be DISTINCT and CONCRETE — never generic placeholders "
    "like 'option A'. The user can also type free text; the frontend "
    "handles that. If the user skips a question, save the answer as "
    "'(tidak diisi user)' and move on so the generator still has minimal "
    "info.\n\n"

    "================  WHEN USER SAYS 'JUST GENERATE'  ================\n"
    "If the user's first message is something like 'buatkan saya paper "
    "lengkap', 'buatin paper', 'langsung generate', 'bikin paper saya', "
    "'lengkap saja', 'generate full paper': DO NOT generate yet. Ask "
    "exactly one question:\n"
    "  'Mau dirapikan dulu (tanya 7 hal: jurusan, topik, latar belakang, "
    "  literatur, metode, data, kesimpulan) atau langsung generate "
    "  dengan default minimal?'\n"
    "  [OPSI]\n"
    "  1) Dirapikan dulu (recommended)\n"
    "  2) Langsung generate dengan default\n"
    "  3) Saya kasih semua info sekaligus\n"
    "  [/OPSI]\n"
    "- Pilih (1) → mulai dari STEP 1.\n"
    "- Pilih (2) → SaveMemory(key=jurusan, value='Teknik'), then call "
    "  GenerateFullPaper(prompt=<topic from first message>).\n"
    "- Pilih (3) → ask the user to write all 7 fields in one message, "
    "  then jump to STEP 8 (CONFIRM).\n\n"

    "================  EDITING EXISTING PAPER  ================\n"
    "Only call Propose* tools when a paper already exists and the user "
    "wants to tweak ONE specific part. Don't assemble a paper through "
    "consecutive ProposeSection calls — use GenerateFullPaper.\n"
    "- Keywords always go through ProposeKeywords.\n"
    "- ProposeJournal and RequestExportDocx auto-apply.\n"
    "- After a Propose* call, write 1-2 sentences explaining what + why.\n"
    "- 'Rapikan' / renumber Fig.+Table+Eq.: when the user says rapikan, "
    "  reorder, perbarui referensi, etc., FIRST call GetPaperNumbering to "
    "  see the current ordered figure/table/equation list, THEN call "
    "  GetPaperContent to read each section's prose, THEN issue one "
    "  ProposeSection per section whose text references stale "
    "  Fig.X / Table Y / Eq. (Z) numbers. Do NOT touch sections that don't "
    "  mention any figure/table/equation.\n\n"

    "================  TOOL HINTS  ================\n"
    "- SaveMemory / GetMemory: use them aggressively to track the 7 "
    "  discovery answers. Always check GetMemory first to avoid asking "
    "  questions the user already answered.\n"
    "- SearchPapers already filters out broken/inaccessible entries — "
    "  just summarize, don't re-filter.\n"
    "- ListAttachedFiles + ReadAttachedFile: always loop over EVERY "
    "  attached file in step 4, not just the first.\n\n"

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


# ── Upstream concurrency control ────────────────────────────────────────────
# Global semaphore caps how many upstream requests we hold open per worker
# process. Without this, when several users (or several papers in the same
# user's tabs) hit /chat at once, all gthread threads block on the upstream
# socket and ApiGW returns 500/429. Cap chosen so 4 workers × 8 threads can
# still serve cheap endpoints (quota, list_papers) while a few heavy chat
# streams are in flight.
_MAX_UPSTREAM_INFLIGHT = int(os.getenv("CHAT_UPSTREAM_INFLIGHT", "3"))
_upstream_sem = threading.BoundedSemaphore(_MAX_UPSTREAM_INFLIGHT)


def _call_upstream(messages, tools, model=None, _allow_no_thinking=True):
    """POST to the upstream chat-completions endpoint with retry/backoff.

    Returns the streaming Response on success (status 200), or None on
    network failure / persistent error. The caller is responsible for
    reading the stream and surfacing an SSE error if the return is None.

    Retry policy:
      - 429 / 5xx        → up to 3 attempts with exponential backoff (0.8s, 1.6s, 3.2s)
      - 400 + thinking   → one retry without thinking (some payloads/tool combos
                           confuse adaptive thinking on the upstream side)
      - persistent 5xx   → fall back to V-CLAUDE → V-GLM (one regional outage
                           on Opus shouldn't take chat down)
      - other            → return as-is
    """
    primary_model = model or MODEL
    # Models to try in order. V-CLAUDE first (most reliable in benchmarks),
    # then Opus for quality, then GLM as last resort. One regional outage
    # on any single backend shouldn't take chat down.
    fallback_chain = [primary_model]
    for fb in ("V-CLAUDE", "V-OPUS", "01/claude-sonnet-4.5-1m", "V-GLM"):
        if fb != primary_model and fb not in fallback_chain:
            fallback_chain.append(fb)

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
    }

    if not _upstream_sem.acquire(timeout=90):
        log.warning("chat._call_upstream: semaphore acquire timeout")
        return None

    try:
        last = None
        for model_idx, current_model in enumerate(fallback_chain):
            payload = dict(base_payload, model=current_model)
            attempts = 3 if model_idx == 0 else 1  # only retry primary heavily
            for attempt in range(attempts):
                try:
                    resp = requests.post(
                        API_URL, headers=headers, json=payload,
                        stream=True, timeout=180,
                    )
                except requests.RequestException as e:
                    log.warning("chat._call_upstream net err model=%s attempt=%d: %s",
                                current_model, attempt, e)
                    last = None
                    time.sleep(0.8 * (2 ** attempt))
                    continue

                if resp.status_code == 200:
                    if model_idx > 0:
                        log.info("chat._call_upstream fallback succeeded with %s", current_model)
                    return resp

                # 400 + thinking → drop thinking and retry the same model.
                if (resp.status_code == 400 and _allow_no_thinking
                        and payload.get("thinking")):
                    resp.close()
                    payload.pop("thinking", None)
                    try:
                        resp2 = requests.post(
                            API_URL, headers=headers, json=payload,
                            stream=True, timeout=180,
                        )
                        if resp2.status_code == 200:
                            return resp2
                        last = resp2
                    except requests.RequestException as e:
                        log.warning("chat._call_upstream no-think err: %s", e)
                        last = None

                # 429 or 5xx → backoff and retry, then fall through to next model.
                if resp.status_code == 429 or 500 <= resp.status_code < 600:
                    last = resp
                    try:
                        body = resp.raw.read(200, decode_content=True)
                        log.warning("chat._call_upstream %s model=%s attempt=%d body=%r",
                                    resp.status_code, current_model, attempt, body[:200])
                    except Exception:
                        pass
                    resp.close()
                    if attempt < attempts - 1:
                        time.sleep(0.8 * (2 ** attempt))
                    continue

                # Other 4xx → return so caller emits a useful error.
                return resp

            # Primary model exhausted retries; try next model in chain.
            if model_idx == 0 and len(fallback_chain) > 1:
                log.warning("chat._call_upstream falling back from %s to %s",
                            current_model, fallback_chain[1])

        return last
    finally:
        _upstream_sem.release()


# Cheap keyword router so we only ship the tools the user is plausibly
# going to want this turn — saves a lot of tokens vs sending all of them.
_TOOL_KEYWORDS = {
    "ProposeTitle":      ("title", "judul"),
    "ProposeAbstract":   ("abstract", "abstrak", "ringkasan"),
    "ProposeKeywords":   ("keyword", "kata kunci"),
    "ProposeSection":    ("section", "bagian", "pendahuluan", "introduction",
                          "metodologi", "methodology", "results", "kesimpulan",
                          "conclusion", "diskusi", "discussion", "literatur",
                          "rapikan", "renumber", "rapikan referensi"),
    "ProposeReference":  ("reference", "referensi", "sitasi", "citation",
                          "daftar pustaka", "bibliography"),
    "ProposeJournal":    ("journal", "jurnal", "template", "ieee", "format"),
    "RequestExportDocx": ("docx", "export", "download", "ekspor", "unduh", "word"),
    "WebSearch":         ("cari ", "search", "google ", "find paper"),
    "WebFetch":          ("buka ", "fetch ", "http://", "https://"),
    "SearchPapers":      ("paper", "literature", "literatur", "slr",
                          "systematic review", "tinjauan pustaka", "referensi terkait",
                          "related work", "state of the art", "sota", "studi pustaka"),
    "RunSLR":            ("slr", "systematic literature", "literatur review",
                          "literature review", "tinjauan pustaka", "studi pustaka",
                          "cari paper", "kumpulkan referensi", "kumpulan paper",
                          "literatur lengkap", "review lengkap"),
    "GetLiterature":     ("literatur saya", "literatur paper", "list literatur",
                          "tabel literatur", "show literature", "lihat literatur",
                          "tampilkan literatur", "literature catalog"),
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
    "GetPaperNumbering": ("rapikan", "renumber", "fig.", "table ", "eq.",
                          "gambar ", "tabel ", "rumus ", "urutkan",
                          "perbarui referensi gambar", "perbarui referensi tabel"),
}

# Default toolset: small + always-relevant. The 7-step DISCOVERY workflow
# needs SaveMemory/GetMemory every turn to track answers, plus search/file
# tools so step 4 (literature review) works without keyword-router gymnastics.
_BASE_TOOLS = {
    "SaveMemory",
    "GetMemory",
    "GetPaperContent",
    "ListAttachedFiles",
    "ReadAttachedFile",
    "SearchPapers",
    "RunSLR",
    "GetLiterature",
    # GenerateFullPaper must be ALWAYS available — the AI hits the CONFIRM step
    # mid-conversation and a keyword like "generate sekarang" alone shouldn't
    # decide whether the tool ships. Without this it would hallucinate a "Job
    # started" reply and never actually call the tool.
    "GenerateFullPaper",
}


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


def _paper_has_active_generation(paper_id, user_id):
    """Return job_id if there is a pending GenerateFullPaper job for this
    paper owned by this user, else None. Self-cleans stale entries."""
    if not paper_id:
        return None
    with _active_jobs_lock:
        job_id = _active_jobs_by_paper.get(paper_id)
    if not job_id:
        return None
    job = AiJob.query.filter_by(id=job_id, user_id=user_id).first()
    if job and job.status in ('pending', 'queued', 'running'):
        return job_id
    # Stale entry — drop it so the next call returns None immediately.
    with _active_jobs_lock:
        cur = _active_jobs_by_paper.get(paper_id)
        if cur == job_id:
            _active_jobs_by_paper.pop(paper_id, None)
    return None


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

    # Lock: if another chat in this paper has a generation job in flight, the
    # user can't kick off a second one or even chat freely on the same paper
    # without confusing the editor's auto-load. Steer them to a different
    # paper or to wait. Cheaper than a DB-backed lock and survives across
    # gunicorn workers via the AiJob.status double-check inside the helper.
    active_job = _paper_has_active_generation(conv.paper_id, user_id)
    if active_job:
        return {
            "error": (
                "Chat lain di paper ini sedang generate paper. "
                "Tunggu selesai (3-10 menit) atau pakai paper lain."
            ),
            "code": "GENERATION_IN_PROGRESS",
            "job_id": active_job,
        }, 409

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
            total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

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

                    try:
                        result = execute_tool(tool_name, args, user_id, conv.paper_id)
                        log.info(f"[TOOL_RESULT] {tool_name} returned: {str(result)[:500]}")
                    except Exception as e:
                        log.error(f"[TOOL_ERROR] {tool_name} failed: {type(e).__name__}: {str(e)}", exc_info=True)
                        result = f"Tool execution error: {type(e).__name__}: {str(e)}"

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
                        elif tool_name == "RunSLR":
                            try:
                                payload = json.loads(result[len("<<PROPOSAL>>"):])
                                upstream_result = (
                                    f"SLR job queued (job_id={payload.get('job_id','?')}, "
                                    f"query={payload.get('query','')!r}, "
                                    f"top_k={payload.get('top_k', 50)}, ai={payload.get('ai_model','V-OPUS')}). "
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

            assistant_msg = ChatMessage(
                conversation_id=conv_id,
                role='assistant',
                content=assistant_content,
                thinking=assistant_thinking if assistant_thinking else None,
                tool_calls=all_tool_calls_data if all_tool_calls_data else None
            )
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
