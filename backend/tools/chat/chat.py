"""
Simple streaming chat — no tools, no memory, no workflow.
User message → inject paper data as context → call AI → stream SSE → save message.
Supports [APPLY_PAPER] tags for direct paper editing from chat.
"""

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

from flask import Blueprint, Response, request, stream_with_context, jsonify, send_file
from flask_jwt_extended import get_jwt_identity, jwt_required

from sqlalchemy import desc

from utils.database.models import ChatMessage, Conversation, Paper, db, safe_commit
import requests as _requests
import urllib3 as _urllib3
from utils.ai_tools.model_router import route_chat_call
from utils.core.redis_client import get_redis
from utils.core.user_storage import get_username, save_chat_send_by_id, save_chat_recv_by_id
from tools.chat.tools import parse_completion, apply_operations, save_thinking_to_fs
from tools.Literatur.literature_helpers import get_pinned_literature

log = logging.getLogger(__name__)

simple_chat = Blueprint("simple_chat", __name__)


def _stream_key(conv_id: str) -> str:
    """Redis key for streaming state."""
    return f"chat:stream:{conv_id}"


def _cancel_key(conv_id: str) -> str:
    """Redis key for cancel flag — separate from stream state to avoid overwrite."""
    return f"chat:cancel:{conv_id}"


def _gen_id():
    return uuid.uuid4().hex


def _current_user_id() -> int | None:
    raw = get_jwt_identity()
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


_system_prompt_cache: str | None = None
_prompt_mtime: float | None = None


def load_system_prompt() -> str:
    global _system_prompt_cache, _prompt_mtime
    path = os.path.join(os.path.dirname(__file__), "chatPrompt.txt")
    try:
        current_mtime = os.path.getmtime(path)
        if _system_prompt_cache is not None and _prompt_mtime == current_mtime:
            return _system_prompt_cache
        with open(path, "r", encoding="utf-8") as f:
            _system_prompt_cache = f.read()
        _prompt_mtime = current_mtime
    except FileNotFoundError:
        log.warning("chatPrompt.txt not found at %s, using fallback prompt", path)
        _system_prompt_cache = (
            "Anda adalah asisten AI yang membantu pengguna menulis paper akademik. "
            "Jawab pertanyaan pengguna dengan jelas dan ringkas."
        )
    return _system_prompt_cache


def get_paper_context(paper_id: str | None) -> str:
    """Build full paper data JSON for the AI system prompt.

    Returns the complete paper JSON so the AI always has up-to-date
    context (title, abstract, sections with full content, references, etc.)
    and can edit it via [APPLY_PAPER] tags.

    Smart truncation: progressively trims section text content and
    reference count while keeping valid JSON structure. This ensures
    the AI can always parse the paper data.
    """
    if not paper_id:
        return ""

    paper = Paper.query.get(paper_id)
    if not paper:
        return f"Paper ID: {paper_id}\n(Paper not found in database.)"

    data = dict(paper.data) if isinstance(paper.data, dict) else {}
    if not data:
        return f"Paper: {paper.title or 'Untitled'}\nPaper ID: {paper_id}\n(Paper data is empty — belum ada konten.)"

    # Always include paper_id in the context for [APPLY_PAPER] operations
    data["_paper_id"] = paper_id

    # Normalize keyed sections → "sections" array so AI sees consistent format
    try:
        from tools.chat.tools import normalize_paper_to_array
        normalize_paper_to_array(data)
        # Strip keyed entries + internal metadata to avoid duplication in context
        import re as _re
        for key in list(data.keys()):
            if _re.match(r'^section\d+[a-z]?$', key):
                del data[key]
        data.pop("_section_keys", None)
    except Exception as e:
        log.warning("Failed to normalize paper data for %s: %s", paper_id, e)

    # Serialize full paper data
    try:
        paper_json = json.dumps(data, indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        paper_json = str(data)

    MAX_CONTEXT = 80000  # raised from 30K — full papers with 60+ refs need this

    if len(paper_json) <= MAX_CONTEXT:
        return paper_json

    # Smart truncation: trim section text content progressively
    import copy as _copy

    d = _copy.deepcopy(data)
    truncated = False

    # Step 1: trim long text blocks in sections (keep 2000 chars per block)
    for sec in d.get("sections", []):
        for block in sec.get("content", []):
            if isinstance(block, dict) and block.get("text") and len(block["text"]) > 2000:
                block["text"] = block["text"][:2000] + "... [dipotong — terlalu panjang]"
                truncated = True

    result = json.dumps(d, indent=2, ensure_ascii=False)
    if len(result) <= MAX_CONTEXT:
        if truncated:
            # Embed truncation note as a JSON property instead of appending
            # (appending after closing brace creates invalid JSON)
            d["_truncated"] = "Beberapa konten section dipotong. Gunakan [APPLY_PAPER] untuk membaca/mengedit section lengkap."
            result = json.dumps(d, indent=2, ensure_ascii=False)
            if len(result) > MAX_CONTEXT:
                # Still too big after adding note — remove and append silently
                d.pop("_truncated", None)
                result = json.dumps(d, indent=2, ensure_ascii=False)
        return result

    # Step 2: trim references (keep 40)
    refs = d.get("references", [])
    if refs and len(refs) > 40:
        kept = refs[:40]
        omitted = len(refs) - 40
        d["references"] = kept
        if "sections" not in d or not isinstance(d.get("sections"), list):
            d["sections"] = []
        d["sections"].append({
            "title": "_SYSTEM_NOTE",
            "content": [{"id": "text", "text": f"… dan {omitted} referensi lain dihilangkan dari konteks untuk menghemat ruang. Tanyakan user jika butuh detail."}],
        })
        truncated = True

    result = json.dumps(d, indent=2, ensure_ascii=False)
    if len(result) <= MAX_CONTEXT:
        if truncated:
            d["_truncated"] = "Paper context dipotong. Gunakan [APPLY_PAPER] untuk mengedit section di luar konteks yang terlihat."
            result = json.dumps(d, indent=2, ensure_ascii=False)
            if len(result) > MAX_CONTEXT:
                d.pop("_truncated", None)
                result = json.dumps(d, indent=2, ensure_ascii=False)
        return result

    # Step 3: harder trim (1000 chars per text block)
    for sec in d.get("sections", []):
        for block in sec.get("content", []):
            if isinstance(block, dict) and block.get("text") and len(block["text"]) > 1000:
                block["text"] = block["text"][:1000] + "... [dipotong]"

    result = json.dumps(d, indent=2, ensure_ascii=False)
    if len(result) > MAX_CONTEXT:
        # If still oversized even after trimming, embed note as property
        d["_truncated"] = "Paper context melebihi 80K chars — beberapa section telah dipangkas. Gunakan [APPLY_PAPER] untuk mengedit section spesifik."
        result = json.dumps(d, indent=2, ensure_ascii=False)
    return result


# ─── Conversation CRUD ─────────────────────────────────────────────────────


@simple_chat.route("/api/chat/papers", methods=["GET"])
@jwt_required()
def list_chat_papers():
    """List papers that have conversations for the current user."""
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return jsonify({'error': 'invalid identity'}), 400
    papers = (
        db.session.query(Paper)
        .join(Conversation, Conversation.paper_id == Paper.id)
        .filter(Conversation.user_id == user_id)
        .distinct()
        .all()
    )
    return jsonify([{"id": p.id, "title": p.title} for p in papers])


@simple_chat.route("/api/papers/<paper_id>/conversations", methods=["GET"])
@jwt_required()
def list_paper_conversations(paper_id):
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Unauthorized"}), 401
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return jsonify({"error": "Paper not found"}), 404
    convs = (
        Conversation.query.filter_by(user_id=user_id, paper_id=paper_id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )
    # Pre-load message counts in a single GROUP BY query to avoid N+1
    conv_ids = [c.id for c in convs]
    msg_counts = {}
    if conv_ids:
        rows = (
            db.session.query(ChatMessage.conversation_id, db.func.count(ChatMessage.id))
            .filter(ChatMessage.conversation_id.in_(conv_ids))
            .group_by(ChatMessage.conversation_id)
            .all()
        )
        msg_counts = dict(rows)
    return jsonify([c.to_dict(message_count=msg_counts.get(c.id, 0)) for c in convs])


@simple_chat.route("/api/papers/<paper_id>/conversations", methods=["POST"])
@jwt_required()
def create_paper_conversation(paper_id):
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Unauthorized"}), 401
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return jsonify({"error": "Paper not found"}), 404
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "New Chat").strip() or "New Chat"
    conv = Conversation(
        id=_gen_id(),
        user_id=user_id,
        paper_id=paper_id,
        title=title,
    )
    db.session.add(conv)
    try:
        safe_commit()
    except Exception:
        db.session.rollback()
        raise
    return jsonify(conv.to_dict())


@simple_chat.route("/api/chat/conversations/<conv_id>", methods=["GET"])
@jwt_required()
def get_conversation(conv_id: str):
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Unauthorized"}), 401
    conv = Conversation.query.filter_by(id=conv_id, user_id=user_id).first()
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404
    msgs = (
        ChatMessage.query.filter_by(conversation_id=conv_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return jsonify({
        **conv.to_dict(),
        "messages": [m.to_dict() for m in msgs],
    })


@simple_chat.route("/api/chat/conversations/<conv_id>", methods=["PATCH"])
@jwt_required()
def rename_conversation(conv_id: str):
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Unauthorized"}), 401
    conv = Conversation.query.filter_by(id=conv_id, user_id=user_id).first()
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Title is required"}), 400
    conv.title = title
    try:
        safe_commit()
    except Exception:
        db.session.rollback()
        raise
    return jsonify({"ok": True})


@simple_chat.route("/api/chat/conversations/<conv_id>", methods=["DELETE"])
@jwt_required()
def delete_conversation(conv_id: str):
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Unauthorized"}), 401
    conv = Conversation.query.filter_by(id=conv_id, user_id=user_id).first()
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404
    # cascade="all, delete-orphan" on relationship handles message deletion
    db.session.delete(conv)
    try:
        safe_commit()
    except Exception:
        db.session.rollback()
        raise
    return jsonify({"ok": True})


@simple_chat.route("/api/chat/conversations/<conv_id>/clear", methods=["POST"])
@jwt_required()
def clear_conversation(conv_id: str):
    """Delete all messages in a conversation but keep the conversation itself."""
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Unauthorized"}), 401
    conv = Conversation.query.filter_by(id=conv_id, user_id=user_id).first()
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404
    deleted = ChatMessage.query.filter_by(conversation_id=conv_id).delete()
    conv.title = "New Chat"
    try:
        safe_commit()
    except Exception:
        db.session.rollback()
        log.exception("clear_conversation: commit failed for conv=%s", conv_id)
        return jsonify({"error": "Failed to clear conversation"}), 500
    log.info("Cleared %d messages from conv=%s", deleted, conv_id)
    return jsonify({"ok": True, "deleted": deleted})


@simple_chat.route("/api/chat/conversations/<conv_id>/messages", methods=["POST"])
@jwt_required()
def send_message(conv_id: str):
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Unauthorized"}), 401

    conv = Conversation.query.filter_by(id=conv_id, user_id=user_id).first()
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404

    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    images = data.get("images") or []  # base64 images: [{"data": "...", "name": "..."}]

    # Detect image-only request (no text, just images)
    image_only = not content and images

    # Auto-generate prompt for image-only
    if image_only:
        content = "Analisis gambar yang saya lampirkan."

    if not content:
        return jsonify({"error": "Message content is required"}), 400
    if len(content) > 2000000:
        return jsonify({"error": "Pesan terlalu panjang (maks 2 juta karakter, termasuk isi file lampiran). Kurangi jumlah file atau coba @slr untuk analisis literatur otomatis."}), 400
    if len(images) > 5:
        return jsonify({"error": "Maksimal 5 gambar per pesan"}), 400

    # ── Pre-flight: warn if payload is large (but don't block) ───────────
    _large_payload_warning = ""
    if len(content) > 50000:
        _large_payload_warning = (
            "\n\n⚠️ **CATATAN**: Data yang dikirim cukup besar (~{}K karakter). "
            "Respons mungkin lebih lambat. Tips: gunakan tab Literatur untuk upload "
            "paper lalu ketik @slr untuk analisis otomatis."
        ).format(len(content) // 1000)

    log.info("simple_chat.send conv=%s user=%s len=%d images=%d image_only=%s", conv_id, user_id, len(content), len(images), image_only)

    # Save user message to database
    try:
        user_msg = ChatMessage(conversation_id=conv_id, role="user", content=content)
        db.session.add(user_msg)

        if conv.title in (None, "", "New Chat"):
            conv.title = (content[:60] + ("\u2026" if len(content) > 60 else "")) or "New Chat"
        safe_commit()
    except Exception as e:
        log.exception("Failed to save user message: %s", e)
        try:
            db.session.rollback()
        except Exception:
            pass
        # Return 200 with SSE error stream so frontend shows proper error message
        def error_stream():
            yield _sse("error", {"message": "Gagal menyimpan pesan ke database. Coba refresh halaman dan kirim lagi."})
            yield _sse("done", {"message_id": None})
        return Response(
            stream_with_context(error_stream()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Get username once for both user and assistant saves
    username = get_username(user_id=user_id)

    # Save user message to filesystem
    try:
        save_chat_send_by_id(
            username=username,
            paper_id=conv.paper_id,
            data={"content": content, "message_id": user_msg.id},
            conv_id=conv_id
        )
    except Exception as e:
        log.warning("Failed to save user message to filesystem: %s", e)

    # Build system prompt with paper context (all errors caught — never fail before SSE stream)
    try:
        system_content = load_system_prompt().rstrip("\n") + "\n\n"
    except Exception as e:
        log.warning("Failed to load system prompt, using fallback: %s", e)
        system_content = "Anda adalah asisten AI yang membantu pengguna menulis paper akademik.\n\n"

    # Inject user settings (language preference, nickname, institution)
    try:
        from utils.database.models import User as UserModel
        current_user = UserModel.query.get(user_id)
        if current_user:
            user_prefs = []
            nickname = current_user.nickname or current_user.name
            if nickname:
                user_prefs.append(f"- Panggil user dengan nama: **{nickname}**")
            institution = current_user.institution or ""
            if institution:
                user_prefs.append(f"- Institusi user: **{institution}**")
            # Language: paper-level > user-level > default 'id'
            lang = current_user.preferred_language or "id"
            if user_prefs:
                system_content += "## User Preferences\n" + "\n".join(user_prefs) + "\n\n"
    except Exception as e:
        log.warning("Failed to inject user preferences into system prompt: %s", e)

    if conv.paper_id:
        try:
            paper_block = get_paper_context(conv.paper_id)
            if paper_block:
                system_content += f"## Paper Context\nBerikut adalah data JSON lengkap paper user saat ini (selalu up-to-date dari database):\n\n```json\n{paper_block}\n```\n\n"
        except Exception as e:
            log.warning("Failed to build paper context for %s: %s", conv.paper_id, e)

    # Resolve language: paper data > user pref > journal template > default "id"
    # Paper language (set by user in JournalTab) takes highest priority,
    # so each paper can have its own language regardless of user's default.
    resolved_lang = "id"
    paper_obj = None  # guard against NameError on exception path
    _from_paper = False
    _from_user = False
    try:
        # Step 1: Paper language (highest priority — per-paper setting)
        if conv.paper_id:
            paper_obj = Paper.query.get(conv.paper_id)
            if paper_obj and isinstance(paper_obj.data, dict):
                paper_lang = paper_obj.data.get("language")
                if paper_lang in ("en", "id"):
                    resolved_lang = paper_lang
                    _from_paper = True
                    log.info("Language resolved from paper data: %s", resolved_lang)
        # Step 2: Fall back to user's preferred language
        if not _from_paper:
            try:
                from utils.database.models import User as _UM
                _u = _UM.query.get(user_id)
                if _u and _u.preferred_language in ("en", "id"):
                    resolved_lang = _u.preferred_language
                    _from_user = True
                    log.info("Language resolved from user pref: %s", resolved_lang)
            except Exception:
                pass
        # Step 3: Fall back to journal template (only if NO explicit setting anywhere)
        if not _from_paper and not _from_user and paper_obj and paper_obj.data.get("journal"):
            try:
                from tools.Journal.template_registry import get_template as _get_tmpl
                _tmpl = _get_tmpl(paper_obj.data["journal"])
                if _tmpl:
                    _tl = _tmpl.language.lower()
                    if _tl.startswith("english"):
                        resolved_lang = "en"
                        log.info("Language resolved from journal template (%s): en", _tmpl.code)
                    elif _tl.startswith("indonesian"):
                        resolved_lang = "id"
                        log.info("Language resolved from journal template (%s): id", _tmpl.code)
            except Exception:
                pass
    except Exception as e:
        log.warning("Failed to resolve language: %s", e)

    # Inject language directive — strong, explicit, with examples
    if resolved_lang == "en":
        lang_instruction = (
            "## ⚠️ LANGUAGE — MANDATORY, DO NOT IGNORE\n"
            "You MUST respond in **English** for ALL output, including:\n"
            "- Chat responses, explanations, suggestions, questions\n"
            "- Paper/editor text (abstract, introduction, conclusion, etc.)\n"
            "- Tool outputs, proposals, summaries, error messages\n\n"
            "Even if the user writes in Indonesian, you MUST reply in English.\n"
            "Example: user asks 'apa itu IoT?' → you reply 'IoT (Internet of Things) is...'\n"
            "Example: user says 'tolong buat abstract' → you write an English abstract.\n\n"
            "The ONLY exception: if the user explicitly asks you to switch languages,\n"
            "e.g. 'now speak Indonesian' or 'jawab dalam bahasa Indonesia'.\n\n"
            "TRANSLATION REQUESTS: If user asks to translate paper content (e.g. 'terjemahkan ke Indonesia'),\n"
            "use [APPLY_PAPER] to translate the content to the target language, then explain in English.\n"
        )
    else:
        lang_instruction = (
            "## ⚠️ BAHASA — WAJIB, JANGAN ABAIKAN\n"
            "Anda WAJIB merespons dalam **Bahasa Indonesia** untuk SEMUA output, termasuk:\n"
            "- Respons chat, penjelasan, saran, pertanyaan\n"
            "- Teks paper/editor (abstrak, pendahuluan, kesimpulan, dll.)\n"
            "- Output tool, proposal, ringkasan, pesan error\n\n"
            "Meskipun user menulis dalam English, Anda WAJIB membalas dalam Bahasa Indonesia.\n"
            "Meskipun FILE LAMPIRAN berbahasa Inggris, Anda TETAP WAJIB merespons dalam Bahasa Indonesia.\n"
            "Contoh: user asks 'what is IoT?' → Anda menjawab 'IoT (Internet of Things) adalah...'\n"
            "Contoh: user says 'make an abstract' → Anda menulis abstrak dalam Bahasa Indonesia.\n\n"
            "PENGECEUALIAN:\n"
            "1. User secara eksplisit meminta bahasa lain: 'now speak English', 'jawab dalam bahasa Inggris'\n"
            "2. User meminta TRANSLASI: 'terjemahkan ke English', 'translate to English', 'convert ke English', 'ubah ke English'\n"
            "   → Dalam kasus ini, GUNAKAN [APPLY_PAPER] untuk menerjemahkan konten paper ke bahasa target,\n"
            "     lalu JELASKAN dalam Bahasa Indonesia apa yang sudah Anda lakukan.\n"
            "   → Contoh: user says 'terjemahkan abstract ke English' → translate abstract via [APPLY_PAPER],\n"
            "     lalu jawab 'Abstrak sudah diterjemahkan ke bahasa Inggris dan diterapkan ke paper.'\n\n"
        )
    system_content += lang_instruction

    # Inject citation style guide from paper data
    try:
        if conv.paper_id:
            if paper_obj and isinstance(paper_obj.data, dict):
                cs = paper_obj.data.get("citation_style")
                if cs:
                    ALLOWED_CITATION_STYLES = {"IEEE", "APA", "MLA", "CHICAGO", "HARVARD", "VANCOUVER", "ACS"}
                    if cs.upper() not in ALLOWED_CITATION_STYLES:
                        log.warning("Invalid citation style: %s", cs)
                        cs = None
                    if cs:
                        from pathlib import Path as _CSPath
                        style_dir = _CSPath(__file__).resolve().parent.parent / "paperfull" / "prompt" / "style"
                        style_file = style_dir / f"{cs.upper()}.txt"
                        if style_file.exists():
                            system_content += f"## CITATION STYLE GUIDE — {cs.upper()}\n{style_file.read_text(encoding='utf-8')}\n\n"
                            log.info("Injected citation style %s into chat for paper=%s", cs, conv.paper_id)
    except Exception as e:
        log.warning("Failed to inject citation style into chat: %s", e)

    # ── Auto-inject attached files into context ──────────────────────
    # Semua file PDF/TXT/MD yang di-upload ke paper otomatis masuk sebagai
    # konteks referensi. Tidak ada batasan jumlah (semua file diambil).
    # Konten file hanya dibatasi panjang per file (5000 chars) untuk menjaga
    # budget konteks, bukan jumlah file.
    if conv.paper_id:
        try:
            from utils.database.models import PaperFile, db as _filedb
            _all_files = (
                _filedb.session.query(PaperFile)
                .filter_by(paper_id=conv.paper_id)
                .order_by(PaperFile.created_at.desc())
                .limit(50)  # max 50 files
                .all()
            )
            if _all_files:
                _file_blocks = []
                _total_file_chars = 0
                _MAX_FILE_CHARS = 200000  # max chars per file (~50K tokens, raised for full content)
                _MAX_TOTAL_FILE_CHARS = 2000000  # max total chars for all files (~500K tokens, raised for full content)
                for _f in _all_files:
                    _text = (_f.extracted_text or "")[:_MAX_FILE_CHARS]
                    if _text:
                        _file_blocks.append(f"**📄 {_f.original_name}** ({_f.ext}):\n{_text}")
                        _total_file_chars += len(_text)
                        if _total_file_chars > _MAX_TOTAL_FILE_CHARS:
                            _file_blocks.append(f"\n... dan {len(_all_files) - (_f.id if hasattr(_f, 'id') else 0)} file lainnya (total {len(_all_files)} file terattach)")
                            break
                if _file_blocks:
                    system_content += "## 📎 Attached Files (reference materials — ALL files from this paper)\n" + "\n\n---\n\n".join(_file_blocks) + "\n\n"
                    log.info("Injected %d attached files (%d chars) into chat for paper=%s", len(_all_files), _total_file_chars, conv.paper_id)
        except Exception as e:
            log.warning("Failed to inject attached files into chat: %s", e)

    # ── @slr tag: inject pinned literature + SLR analysis template ─────────
    # User ketik @slr → ambil literatur pinned + inject SLR analysis template
    # (template moved out of base chatPrompt.txt to save ~140 lines per msg)
    # Tag @slr dihapus dari pesan sebelum ke AI HANYA jika literatur berhasil.
    slr_tag_detected = False
    _needs_slr_template = False  # whether to inject SLR analysis instructions
    if "@slr" in content.lower():
        slr_tag_detected = True
        _needs_slr_template = True
        if conv.paper_id:
            try:
                pinned_text = get_pinned_literature(conv.paper_id, user_id, max_items=10)
                if pinned_text:
                    system_content += f"## SLR References (Pinned)\n{pinned_text}\n\n"
                    content = re.sub(r"@slr\b", "", content, flags=re.IGNORECASE).strip()
                    log.info("@slr tag: injected %d pinned literature items for paper=%s", pinned_text.count("\n[") + 1, conv.paper_id)
                else:
                    system_content += "## SLR Note\nUser used @slr but no pinned literature found for this paper. Suggest running an SLR search.\n\n"
                    log.info("@slr tag: no pinned literature for paper=%s, keeping tag in message", conv.paper_id)
            except Exception as e:
                log.warning("@slr tag: failed to load pinned literature: %s", e)
        else:
            content = re.sub(r"@slr\b", "", content, flags=re.IGNORECASE).strip()

    # ── Detect research gap/SLR intent for conditional template injection ──
    # Keywords in user message that need SLR analysis template
    _SLR_KEYWORDS = ["riset gap", "research gap", "review literatur", "literature review",
                     "slr analysis", "systematic review", "gap analysis",
                     "celah riset", "analisis gap"]
    _content_lower = content.lower()
    if not _needs_slr_template:
        for kw in _SLR_KEYWORDS:
            if kw in _content_lower:
                _needs_slr_template = True
                break

    # Inject SLR analysis template (only when needed — saves ~140 lines of tokens)
    if _needs_slr_template:
        try:
            _slr_prompt_path = os.path.join(os.path.dirname(__file__), "slrAnalysisPrompt.txt")
            with open(_slr_prompt_path, "r", encoding="utf-8") as _f:
                system_content += _f.read() + "\n\n"
            log.info("SLR analysis template injected for conv=%s (keyword/slr tag)", conv_id)
        except Exception as e:
            log.warning("Failed to load SLR analysis template: %s", e)

    # ── @draft tag: inject named chat drafts into system prompt ───────────
    # User writes "@draft <name>" or "@draft name1,name2" → fetch those drafts
    # and inject as context. Tag removed from message before AI call.
    draft_tag_detected = False
    if conv.paper_id:
        # BUG-23: Limit input before parsing to prevent ReDoS (max 500 chars)
        _draft_search_input = content[:500]
        # Non-regex parse: find "@draft" token, take the rest of that line as
        # a comma-separated list of names. Avoids the nested-quantifier regex
        # r"@draft\s+([^\s@]+(?:\s*,\s*[^\s@]+)*)" which is ReDoS-prone.
        _lower = _draft_search_input.lower()
        _tag_pos = _lower.find("@draft")
        if _tag_pos != -1:
            # Position just after the literal "@draft"
            _after = _tag_pos + len("@draft")
            _rest = _draft_search_input[_after:]
            # Names must be preceded by whitespace ("@draft name", not "@drafting")
            if _rest[:1] in (" ", "\t"):
                _stripped = _rest.lstrip(" \t")
                _consumed_ws = len(_rest) - len(_stripped)
                # Consume a contiguous comma-separated list of name tokens.
                # A name token = run of non-space, non-comma, non-@ chars.
                # Optional spaces are allowed only immediately around commas.
                # Linear scan (no regex backtracking) → no ReDoS.
                i = 0
                names: list[str] = []
                cur = []
                n = len(_stripped)
                while i < n:
                    ch = _stripped[i]
                    if ch in (" ", "\t"):
                        # Look ahead: spaces are part of the list only if a comma
                        # follows (possibly after more spaces). Otherwise the list ends.
                        j = i
                        while j < n and _stripped[j] in (" ", "\t"):
                            j += 1
                        if j < n and _stripped[j] == ",":
                            i = j  # jump to the comma; comma handler advances
                            continue
                        break  # end of name list
                    if ch == ",":
                        if cur:
                            names.append("".join(cur))
                            cur = []
                        i += 1
                        # skip spaces after comma
                        while i < n and _stripped[i] in (" ", "\t"):
                            i += 1
                        continue
                    if ch == "@" or ch == "\n":
                        break
                    cur.append(ch)
                    i += 1
                if cur:
                    names.append("".join(cur))
                names = [x.strip() for x in names if x.strip()]
                # Total chars consumed from the original (post-@draft) rest string
                _match_len = len("@draft") + _consumed_ws + i
            else:
                names = []
                _match_len = 0
            if names:
                draft_tag_detected = True
                # Remove the whole "@draft ..." span from user content
                _match_end = _tag_pos + _match_len
                content = (content[:_tag_pos].strip() + " " + content[_match_end:].strip()).strip()
                content = re.sub(r"\s+", " ", content).strip()
                try:
                    from tools.chat.drafts import get_drafts_by_names
                    draft_block = get_drafts_by_names(conv.paper_id, user_id, names, max_items=5)
                    if draft_block:
                        system_content += f"## Chat Drafts (user-curated context)\n{draft_block}\n\n"
                        log.info("@draft tag: injected %d draft(s) for paper=%s names=%s", draft_block.count("### Draft:"), conv.paper_id, names)
                    else:
                        log.info("@draft tag: no matching drafts found for names=%s paper=%s", names, conv.paper_id)
                except Exception as e:
                    log.warning("@draft tag: failed to load drafts: %s", e)

    # ── @tabel / @grafik tag: inject data items into system prompt ──────
    # User ketik @tabel atau @grafik di pesan → ambil data items dari paper
    # dan injeksi sebagai context. Tag dihapus dari pesan sebelum ke AI.
    data_tag_detected = False
    if conv.paper_id and ("@tabel" in content.lower() or "@grafik" in content.lower()):
        data_tag_detected = True
        # Hapus tag dari konten user
        content = re.sub(r"@(tabel|grafik)\b", "", content, flags=re.IGNORECASE).strip()
        try:
            from tools.data.data_jobs import get_data_items_for_paper
            data_text = get_data_items_for_paper(conv.paper_id, user_id, max_tables=10, max_charts=10)
            if data_text:
                system_content += f"## Data Items (Tabel & Grafik)\n{data_text}\n\n"
                log.info("@tabel/@grafik tag: injected data items for paper=%s", conv.paper_id)
            else:
                log.info("@tabel/@grafik tag: no data items for paper=%s", conv.paper_id)
        except Exception as e:
            log.warning("@tabel/@grafik tag: failed to load data items: %s", e)

    # ── 📷 Image analysis: VIOLA-IMAGE ────────────────────────────────────
    # Image-only request → call VIOLA-IMAGE directly and return as response
    # Image + text → inject analysis into system prompt for chat model
    image_analysis_text = ""
    if images:
        try:
            from tools.chat.image_analysis import analyze_images
            image_analysis_text = analyze_images(images, user_prompt=content)

            # Check if analysis failed (returned error messages instead of actual analysis)
            if "[Image analysis failed" in image_analysis_text or "[Image analysis:" in image_analysis_text:
                log.warning("Image analysis returned errors for conv=%s: %s", conv_id, image_analysis_text[:200])
                # Return error to user instead of continuing with failed analysis
                def error_stream():
                    yield _sse("error", {"message": f"Gagal menganalisa gambar. Error: {image_analysis_text[:200]}"})
                    yield _sse("done", {"message_id": None})
                return Response(
                    stream_with_context(error_stream()),
                    mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                )

            if image_only and image_analysis_text:
                # Image-only: return analysis directly as assistant response
                log.info("Image-only request: returning VIOLA-IMAGE analysis directly for conv=%s", conv_id)

                # Save user message to filesystem (already done at lines 346-354, but re-save with image metadata)
                # Note: user message already saved by standard flow above, skip duplicate

                # Save assistant message to DB
                try:
                    assistant_msg = ChatMessage(
                        conversation_id=conv_id,
                        role="assistant",
                        content=image_analysis_text
                    )
                    db.session.add(assistant_msg)
                    safe_commit()
                except Exception as e:
                    log.exception("Failed to save assistant message: %s", e)
                    db.session.rollback()
                    # Return error as SSE stream
                    def error_stream():
                        yield _sse("error", {"message": "Gagal menyimpan hasil analisa gambar."})
                        yield _sse("done", {"message_id": None})
                    return Response(
                        stream_with_context(error_stream()),
                        mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                    )

                # Save assistant message to filesystem
                try:
                    save_chat_recv_by_id(
                        username=username,
                        paper_id=conv.paper_id,
                        data={
                            "content": image_analysis_text,
                            "role": "assistant",
                            "message_id": assistant_msg.id,
                        },
                        conv_id=conv_id
                    )
                except Exception as e:
                    log.warning("Failed to save assistant message to filesystem: %s", e)

                # Return as SSE stream (direct response)
                def image_analysis_stream():
                    yield _sse("text", {"content": image_analysis_text})
                    yield _sse("done", {"message_id": assistant_msg.id})

                return Response(
                    stream_with_context(image_analysis_stream()),
                    mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                )

            elif image_analysis_text:
                # Image + text: inject analysis into system prompt
                system_content += image_analysis_text + "\n\n"
                log.info("Image analysis injected: %d images, %d chars for conv=%s",
                         len(images), len(image_analysis_text), conv_id)
        except Exception as e:
            log.warning("Image analysis failed for conv=%s: %s", conv_id, e)

    # ── Search tool integration ───────────────────────────────────────────
    # Detect user intent and run searches BEFORE calling AI, so the AI
    # has real data to work with.
    search_context = ""
    slr_offer_needed = False
    intents = []  # accessible later for Phase 1.5 fallback
    try:
        from tools.chat.search_tools import detect_intent, execute_searches
        intents = detect_intent(content)
        if intents:
            log.info("Chat search intents detected: %s for conv=%s", intents, conv_id)
            search_result = execute_searches(intents, content, limit=8)
            if search_result["context"]:
                search_context = search_result["context"] + "\n\n"
            slr_offer_needed = search_result.get("needs_slr_offer", False)
    except Exception as e:
        log.warning("Search tool integration error: %s", e)

    if search_context:
        system_content += search_context

    if slr_offer_needed:
        if not _needs_slr_template:
            _needs_slr_template = True
            # Inject SLR analysis template for research gap intents
            try:
                _slr_prompt_path = os.path.join(os.path.dirname(__file__), "slrAnalysisPrompt.txt")
                with open(_slr_prompt_path, "r", encoding="utf-8") as _f:
                    system_content += _f.read() + "\n\n"
                log.info("SLR analysis template injected for conv=%s (search intent)", conv_id)
            except Exception as e:
                log.warning("Failed to load SLR analysis template: %s", e)
        system_content += (
            "## INSTRUKSI SLR\n"
            "User meminta analisis research gap atau systematic literature review.\n"
            "Jika hasil pencarian di atas SUDAH cukup untuk menjawab pertanyaan user, "
            "jawab langsung berdasarkan data tersebut.\n"
            "Jika user membutuhkan analisis LEBIH MENDALAM (puluhan paper, scoring, "
            "dedup, ringkasan per paper), tawarkan fitur SLR lengkap dengan format:\n\n"
            "---\n"
            "💡 **Butuh analisis lebih mendalam?** Saya bisa menjalankan "
            "**Systematic Literature Review (SLR)** lengkap yang akan:\n"
            "- Mencari dari 10+ database akademik (Semantic Scholar, ArXiv, CrossRef, IEEE, Scopus, dll)\n"
            "- Scoring & ranking otomatis berdasarkan sitasi & relevansi\n"
            "- Deduplikasi otomatis\n"
            "- Ringkasan AI per paper\n\n"
            "Ketik **\"ya, jalankan SLR\"** untuk memulai, atau **\"lanjutkan saja\"** "
            "untuk menggunakan hasil pencarian di atas.\n"
            "---\n\n"
        )

    # ── SLR confirmation detection ────────────────────────────────────────
    # If user's message is a confirmation to run SLR (e.g. "ya jalankan SLR",
    # "iya SLR", "yes run SLR"), trigger the SLR job directly.
    slr_triggered = False
    slr_job_info = None
    _SLR_CONFIRM_PATTERNS = [
        r"(?:ya|iya|yes|yoi|oke|ok|yup)\b.*(?:slr|systematic|literature review)",
        r"(?:jalankan|mulai|run|start|lakukan|lakukan saja)\b.*(?:slr|systematic)",
        r"(?:slr|systematic)\b.*(?:ya|iya|yes|oke|ok|jalankan|mulai)",
    ]
    for pattern in _SLR_CONFIRM_PATTERNS:
        if re.search(pattern, content.lower()):
            slr_triggered = True
            break

    if slr_triggered and conv.paper_id:
        try:
            from tools.chat.search_tools import trigger_slr_job
            slr_job_info = trigger_slr_job(
                paper_id=conv.paper_id,
                user_id=user_id,
                query=content,
                conversation_id=conv_id,
            )
            log.info("SLR job triggered from chat: %s", slr_job_info)
        except Exception as e:
            log.warning("Failed to trigger SLR from chat: %s", e)

    # Pre-fetch chat history outside generator (avoids DB query mid-stream)
    _history = (
        ChatMessage.query.filter_by(conversation_id=conv.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(20)
        .all()
    )
    _history.reverse()

    def generate():
        assistant_content = ""
        thinking_content = ""
        model_used = ""
        _token_count = 0
        _r = get_redis()
        log.info("Chat generate started for conv_id=%s", conv_id)

        # Capture system_content from enclosing scope (BUGFIX: assignments
        # below make Python treat it as local → UnboundLocalError at line 1072)
        _sys = system_content

        # Save streaming state to Redis (for reconnect after refresh)
        my_stream_id = uuid.uuid4().hex[:8]
        stream_state = {
            "status": "streaming",
            "conv_id": conv_id,
            "content": "",
            "thinking": "",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "stream_id": my_stream_id,
        }
        try:
            if _r:
                _r.setex(_stream_key(conv_id), 1800, json.dumps(stream_state))  # 30 min TTL
        except Exception as e:
            log.warning("Failed to save initial stream state: %s", e)

        # If SLR was triggered, notify frontend immediately
        if slr_triggered and slr_job_info and slr_job_info.get("success"):
            yield _sse("slr_job_started", {
                "job_id": slr_job_info.get("job_id"),
                "status": slr_job_info.get("status"),
                "message": "SLR job started — akan berjalan di background. Pantau progress di tab Literatur."
            })
        elif slr_triggered and slr_job_info and not slr_job_info.get("success"):
            yield _sse("slr_job_error", {
                "error": slr_job_info.get("error", "Unknown error"),
                "message": "Gagal memulai SLR job. Coba lagi atau gunakan tab Literatur secara manual."
            })

        # ── Resilience tracking (item: streaming must finish in backend even
        #    if the frontend errors / navigates away mid-stream) ─────────────
        # The AI response handles + current phase are captured so that, on a
        # client disconnect (GeneratorExit), we can drain the remaining AI
        # tokens and still persist the completion to the DB.
        response_p1 = None
        response_p2 = None
        _phase = 0           # 1 = collecting phase-1, 2 = synthesizing phase-2
        _finalized = False   # guard so finalization runs at most once

        def _persist_chat_final(final_content: str, thinking: str) -> dict:
            """Parse ops + apply to paper + save assistant message to DB/FS +
            mark Redis 'done'. NON-yielding so it is safe to call from both the
            normal completion path and the client-disconnect path. Runs once.

            DB write uses a fresh connection with retry to survive the stale
            'SSL connection has been closed unexpectedly' that long streams hit.
            """
            nonlocal _finalized, model_used
            out = {"message_id": None, "content": final_content,
                   "paper_applied": None, "ask_user": None, "empty": False,
                   "docx_url": None, "docx_filename": None}
            if _finalized:
                return out
            _finalized = True
            try:
                parsed = parse_completion(final_content or "")
                content = final_content or ""
                if parsed["has_operations"] and conv.paper_id:
                    try:
                        result = apply_operations(conv.paper_id, parsed["operations"], user_id=user_id)
                        out["paper_applied"] = {
                            "operations": parsed["operations"],
                            "results": result.get("results", []),
                            "errors": result.get("errors", []),
                            "success": result.get("success", False),
                        }
                    except Exception as e:
                        log.exception("apply_operations failed during finalize")
                        out["paper_applied"] = {
                            "operations": parsed["operations"],
                            "results": [],
                            "errors": ["Apply gagal: Internal server error"],
                            "success": False,
                        }
                    content = parsed["cleaned_text"] or content
                if parsed["has_ask_user"] and parsed["ask_user"]:
                    out["ask_user"] = parsed["ask_user"]
                    if parsed["cleaned_text"]:
                        content = parsed["cleaned_text"]

                # ── [GENERATE_DOCX]: Render JSON spec to .docx file ──────
                if parsed["has_docx"] and parsed["docx_spec"]:
                    try:
                        from tools.chat.docx_renderer import render_docx
                        import re as _re
                        from pathlib import Path as _Path

                        docx_spec = parsed["docx_spec"]
                        safe_title = _re.sub(r'[^a-zA-Z0-9_\-]+', '_', str(docx_spec.get("title", "document"))).strip("_")[:60] or "document"
                        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
                        docx_filename = f"{safe_title}_{ts}.docx"

                        # Storage path: user/<username>/<paper_id>/chat_docs/<conv_id>/
                        if conv.paper_id:
                            from utils.core.user_storage import get_username as _get_uname
                            _uname = _get_uname(user_id=user_id)
                        else:
                            _uname = f"user_{user_id}"
                        # USER_BASE defined at module level (same as main.py)
                        _chat_docs_dir = _Path(__file__).resolve().parent.parent.parent / "user" / _uname / (conv.paper_id or "global") / "chat_docs" / conv_id
                        _chat_docs_dir.mkdir(parents=True, exist_ok=True)
                        _docx_path = _chat_docs_dir / docx_filename

                        render_docx(docx_spec, _docx_path)
                        out["docx_url"] = f"/api/chat/conversations/{conv_id}/files/{docx_filename}"
                        out["docx_filename"] = docx_filename
                        log.info("GENERATE_DOCX: rendered %s (%d bytes)", docx_filename, _docx_path.stat().st_size)
                    except Exception as docx_err:
                        log.warning("GENERATE_DOCX rendering failed: %s", docx_err)
                        # Don't fail the whole response — just log the error

                # Strip search tags from final content (Phase 2 AI sometimes leaks tags as text)
                from tools.chat.search_tools import strip_search_tags as _sst
                content = _sst(content)

                out["content"] = content

                if content and content.strip():
                    from sqlalchemy.exc import DBAPIError, OperationalError
                    import time as _t
                    mid = None
                    for _attempt in range(3):
                        try:
                            try:
                                db.session.rollback()
                            except Exception:
                                pass
                            msg = ChatMessage(
                                conversation_id=conv_id,
                                role="assistant",
                                content=content,
                                thinking=thinking if thinking else None,
                            )
                            db.session.add(msg)
                            safe_commit()
                            mid = msg.id
                            break
                        except (OperationalError, DBAPIError) as _e:
                            try:
                                db.session.rollback()
                            except Exception:
                                pass
                            log.warning("Chat DB save attempt %d failed (stale conn): %s", _attempt + 1, _e)
                            _t.sleep(0.3 * (_attempt + 1))
                        except Exception:
                            try:
                                db.session.rollback()
                            except Exception:
                                pass
                            log.exception("Chat DB save failed (non-retryable)")
                            break
                    out["message_id"] = mid
                    if mid:
                        try:
                            fs_data = {"content": content, "message_id": mid,
                                       "model": model_used, "conv_id": conv_id}
                            if thinking:
                                fs_data["thinking"] = thinking
                            save_chat_recv_by_id(username=username, paper_id=conv.paper_id,
                                                 data=fs_data, conv_id=conv_id)
                        except Exception as _e:
                            log.warning("FS save failed during finalize: %s", _e)
                        stream_state["status"] = "done"
                        stream_state["message_id"] = mid
                        stream_state["content"] = content
                        try:
                            if _r:
                                _r.setex(_stream_key(conv_id), 60, json.dumps(stream_state))
                        except Exception as _e:
                            log.warning("Redis setex (finalize done) failed conv=%s: %s", conv_id, _e)
                    else:
                        stream_state["status"] = "error"
                        stream_state["error"] = "DB save failed"
                        try:
                            if _r:
                                _r.setex(_stream_key(conv_id), 60, json.dumps(stream_state))
                        except Exception as _e:
                            log.warning("Redis setex (finalize error) failed conv=%s: %s", conv_id, _e)
                else:
                    out["empty"] = True
                    stream_state["status"] = "error"
                    stream_state["error"] = "Empty response"
                    try:
                        if _r:
                            _r.setex(_stream_key(conv_id), 60, json.dumps(stream_state))
                    except Exception as _e:
                        log.warning("Redis setex (finalize empty) failed conv=%s: %s", conv_id, _e)
            except Exception:
                log.exception("Finalize failed for conv=%s", conv_id)
            return out

        def _drain_remaining():
            """Client disconnected — keep consuming the open AI stream so the
            completion is captured, then persist. No yields."""
            nonlocal assistant_content, thinking_content
            try:
                _acc = ""
                _resp = response_p2 if (_phase == 2 and response_p2 is not None) else None
                if _resp is None and _phase == 1 and response_p1 is not None and not assistant_content:
                    _resp = response_p1
                if _resp is not None:
                    for _line in _resp.iter_lines():
                        if not _line:
                            continue
                        if isinstance(_line, bytes):
                            _line = _line.decode("utf-8", "ignore")
                        if not _line.startswith("data: "):
                            continue
                        _ds = _line[6:]
                        if _ds == "[DONE]":
                            break
                        try:
                            _chunk = json.loads(_ds)
                        except json.JSONDecodeError:
                            continue
                        _ch = _chunk.get("choices", [])
                        if not _ch:
                            continue
                        _delta = _ch[0].get("delta", {})
                        _c = _delta.get("content")
                        if _c:
                            _acc += _c
                        _t = (_delta.get("thinking") or _delta.get("reasoning_content")
                              or _delta.get("reasoning") or _delta.get("thinking_content"))
                        if _t:
                            if isinstance(_t, dict):
                                _t = _t.get("content", "")
                            if _t:
                                thinking_content += _t
                    if _resp is response_p2:
                        assistant_content += _acc
                    else:
                        assistant_content = (assistant_content or "") + _acc
            except Exception:
                log.warning("Drain after disconnect failed for conv=%s", conv_id, exc_info=True)
            finally:
                # Close response connections to release underlying sockets
                try:
                    if response_p1:
                        response_p1.close()
                except Exception as _e:
                    log.warning("response_p1.close failed conv=%s: %s", conv_id, _e)
                try:
                    if response_p2:
                        response_p2.close()
                except Exception as _e:
                    log.warning("response_p2.close failed conv=%s: %s", conv_id, _e)
            _persist_chat_final(assistant_content, thinking_content)

        try:
            # ── System prompt truncation ──────────────────────────────────
            # Prevent context overflow when user sends large input (e.g. 70+ papers).
            # Cap system_content at ~80K chars; if exceeded, truncate the paper
            # context block first (least critical), then trim evenly.
            MAX_SYSTEM_CHARS = 2000000
            if len(_sys) > MAX_SYSTEM_CHARS:
                log.warning("System content %d chars exceeds max %d — truncating",
                           len(_sys), MAX_SYSTEM_CHARS)
                # Try to find and truncate "## Paper Context" block first
                _pc_marker = "## Paper Context"
                _pc_idx = _sys.find(_pc_marker)
                _available = MAX_SYSTEM_CHARS - (len(_sys) - (_sys.find("\n", _pc_idx + 50) if _pc_idx != -1 else 0))
                if _pc_idx != -1:
                    # Keep everything before Paper Context, truncate Paper Context
                    _before = _sys[:_pc_idx]
                    _after_pc = _sys[_pc_idx:]
                    _max_pc = max(500, _available - len(_before) - 200)
                    if _max_pc > 0:
                        _pc_end = _sys.find("```", _pc_idx + 200)
                        if _pc_end != -1:
                            # Truncate JSON: keep first _max_pc chars
                            _truncated_pc = _after_pc[:_max_pc] + "\n... (truncated — too many papers for chat)"
                            _sys = _before + _truncated_pc
                        else:
                            _sys = _sys[:MAX_SYSTEM_CHARS]
                    else:
                        _sys = _sys[:MAX_SYSTEM_CHARS]
                else:
                    _sys = _sys[:MAX_SYSTEM_CHARS]
                _sys += ("\n\n⚠️ **SYSTEM NOTE**: Data dipotong karena terlalu besar. "
                                   "Gunakan tab Literatur + @slr untuk analisis paper dalam jumlah banyak.\n")
                log.info("System content truncated to %d chars", len(_sys))

            # Inject large-payload warning into system prompt
            if _large_payload_warning:
                _sys += _large_payload_warning + "\n\n"

            # Build message list: system + history + current user message
            messages_phase1 = [{"role": "system", "content": _sys}]

            for msg in _history:
                role = msg.role if msg.role in ("user", "assistant") else "user"
                messages_phase1.append({"role": role, "content": msg.content})

            # ── PHASE 1: Collect AI response (may contain search tags) ────
            # We collect silently — no streaming to user yet.
            # If AI outputs [WEBSEARCH:query], [ARXIV:query], [SCHOLAR:query]
            # tags, we intercept, execute searches, show progress, then call
            # AI again with real results.
            phase1_text = ""
            phase1_thinking = ""

            _phase = 1
            response_p1, model_used = route_chat_call(
                json={
                    "messages": messages_phase1,
                    "stream": True,
                    "max_tokens": 65536,
                    "reasoning": {"effort": "high"},
                },
                stream=True,
                timeout=1800,
            )

            _phase1_stream_ok = True
            try:
                for line in response_p1.iter_lines():
                    if not line:
                        continue
                    if isinstance(line, bytes):
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
                        phase1_text += delta["content"]
                    thinking_raw = (
                        delta.get("thinking")
                        or delta.get("reasoning_content")
                        or delta.get("reasoning")
                        or delta.get("thinking_content")
                    )
                    if thinking_raw:
                        if isinstance(thinking_raw, dict):
                            thinking_raw = thinking_raw.get("content", "")
                        if thinking_raw:
                            phase1_thinking += thinking_raw
                            # Stream thinking character-by-character
                            yield _sse("thinking", {"content": thinking_raw})
                            # Update Redis state (throttle: every 20 chunks or ~160 chars)
                            _token_count += 1
                            if _token_count % 20 == 0:
                                stream_state["thinking"] = phase1_thinking
                                try:
                                    if _r:
                                        _r.setex(_stream_key(conv_id), 1800, json.dumps(stream_state))
                                except Exception as _e:
                                    log.warning("Redis setex (thinking) failed conv=%s: %s", conv_id, _e)
            except (_requests.exceptions.ChunkedEncodingError, _urllib3.exceptions.ProtocolError) as _stream_err:
                _phase1_stream_ok = False
                log.warning("Phase 1 stream ended prematurely conv=%s: %s — using partial content (%d chars)",
                           conv_id, _stream_err, len(phase1_text))
                if phase1_text:
                    yield _sse("text", {"content": phase1_text})

            # Signal end of thinking phase (before content starts)
            if phase1_thinking:
                yield _sse("thinking_done", {})
                thinking_content = phase1_thinking

            # ── Check for search tags in phase 1 response ─────────────
            search_tags = []
            search_results_context = ""  # initialized here for fallback access
            try:
                from tools.chat.search_tools import extract_search_tags
                search_tags = extract_search_tags(phase1_text)
            except Exception as e:
                log.warning("Failed to extract search tags: %s", e)

            # ── SMART VALIDATION: Skip search tags if user isn't actually asking for search ──
            # Even if the AI generated tags or detect_intent flagged an intent,
            # we double-check the user message to avoid false-positive searches.
            if search_tags:
                try:
                    from tools.chat.search_tools import _has_non_search_keywords
                    if _has_non_search_keywords(content):
                        log.info("Phase 1.5 guard: user message contains non-search keywords — "
                                 "discarding %d AI-generated search tags (conv=%s)",
                                 len(search_tags), conv_id)
                        search_tags = []
                except Exception as e:
                    log.warning("Phase 1.5 guard check failed: %s", e)

            # ── FALLBACK: Auto-generate search tags for academic intents ──
            # If AI didn't output search tags but user asked for academic papers,
            # force-run Literatur fetchers so real data appears in the UI.
            _ACADEMIC_INTENTS = {"academic_search", "research_gap", "arxiv_search"}
            if not search_tags and any(i in _ACADEMIC_INTENTS for i in intents):
                # Double-check: skip fallback if user message is clearly non-search
                try:
                    from tools.chat.search_tools import _has_non_search_keywords
                    if _has_non_search_keywords(content):
                        log.info("Fallback guard: non-search keywords in message — "
                                 "skipping fallback tag generation (conv=%s)", conv_id)
                        search_tags = []
                    else:
                        from tools.chat.search_tools import clean_search_query
                        _clean_q = clean_search_query(content)
                        if _clean_q:
                            # Determine how many papers user wants
                            from tools.chat.search_tools import parse_requested_count
                            _req_n = parse_requested_count(content)
                            _fb_limit = _req_n if _req_n > 0 else 10
                            # Use more fetchers if user wants many papers
                            if _req_n >= 30:
                                search_tags = [
                                    {"type": "openalex", "query": _clean_q, "raw": f"[OPENALEX:{_clean_q}]"},
                                    {"type": "crossref", "query": _clean_q, "raw": f"[CROSSREF:{_clean_q}]"},
                                    {"type": "semantic_scholar", "query": _clean_q, "raw": f"[SEMANTIC_SCHOLAR:{_clean_q}]"},
                                    {"type": "crossref_publishers", "query": _clean_q, "raw": f"[PUBLISHERS:{_clean_q}]"},
                                    {"type": "scopus", "query": _clean_q, "raw": f"[SCOPUS:{_clean_q}]"},
                                ]
                            else:
                                search_tags = [
                                    {"type": "openalex", "query": _clean_q, "raw": f"[OPENALEX:{_clean_q}]"},
                                    {"type": "crossref", "query": _clean_q, "raw": f"[CROSSREF:{_clean_q}]"},
                                    {"type": "semantic_scholar", "query": _clean_q, "raw": f"[SEMANTIC_SCHOLAR:{_clean_q}]"},
                                    {"type": "crossref_publishers", "query": _clean_q, "raw": f"[PUBLISHERS:{_clean_q}]"},
                                ]
                            log.info("Fallback: auto-generated %d search tags for academic intent (conv=%s, query='%s', target=%d)",
                                     len(search_tags), conv_id, _clean_q[:60], _req_n)
                except Exception as e:
                    log.warning("Fallback search tag generation failed: %s", e)

            # ── If no search tags → single-phase: stream phase 1 directly ─
            if not search_tags:
                # Signal composing phase, then stream text in chunks
                assistant_content = phase1_text
                yield _sse("composing_start", {})

                # Stream text in small chunks (not all at once)
                _chunk_size = 8
                _text_to_stream = phase1_text
                # Persist thinking up-front so a refresh mid-replay can render
                # the reasoning block immediately (it's already complete here).
                if phase1_thinking:
                    stream_state["thinking"] = phase1_thinking
                for _i in range(0, len(_text_to_stream), _chunk_size):
                    _chunk = _text_to_stream[_i:_i + _chunk_size]
                    _token_count += 1
                    yield _sse("text", {"content": _chunk})
                    # Persist progressive content to Redis every ~20 chunks so a
                    # page refresh mid-replay resumes from the live position
                    # instead of showing nothing until the stream completes.
                    if _token_count % 20 == 0:
                        stream_state["content"] = _text_to_stream[:_i + _chunk_size]
                        if _r:
                            try:
                                _r.setex(_stream_key(conv_id), 1800, json.dumps(stream_state))
                            except Exception:
                                pass
                            # Check cancel using separate key
                            try:
                                _cancel_raw = _r.get(_cancel_key(conv_id))
                                if _cancel_raw == my_stream_id:
                                    # Mark cancelled in Redis (bug 4), save partial (bug 3)
                                    stream_state["status"] = "cancelled"
                                    try:
                                        _r.setex(_stream_key(conv_id), 60, json.dumps(stream_state))
                                    except Exception:
                                        pass
                                    _persist_chat_final(assistant_content, phase1_thinking)
                                    yield _sse("done", {"message_id": None, "cancelled": True})
                                    return
                            except (json.JSONDecodeError, KeyError):
                                pass
                # Update Redis state
                stream_state["content"] = assistant_content
                try:
                    if _r:
                        _r.setex(_stream_key(conv_id), 1800, json.dumps(stream_state))
                except Exception:
                    pass
                # Close phase 1 response to release the underlying socket
                try:
                    response_p1.close()
                except Exception:
                    pass

            else:
                # ── PHASE 1.5: Execute searches with real-time progress ──
                log.info("Search tags found: %d — executing for conv=%s", len(search_tags), conv_id)

                # Thinking already streamed above during phase 1 loop

                from tools.chat.search_tools import (
                    execute_tag_search,
                    format_search_event_for_frontend,
                    format_search_results_for_ai,
                    parse_requested_count,
                )

                # Parse how many papers the user wants
                _requested_count = parse_requested_count(content)
                if _requested_count > 0:
                    log.info("User requested %d papers — fetching accordingly (conv=%s)", _requested_count, conv_id)
                _fetch_limit = _requested_count if _requested_count > 0 else 20

                all_search_results = []
                _search_total = len(search_tags)
                _running_count = 0
                _search_msg = f"🔍 Mencari {_search_total} sumber referensi"
                if _requested_count > 0:
                    _search_msg += f" (target: {_requested_count} paper)"
                _search_msg += "..."
                yield _sse("search_phase_start", {
                    "message": _search_msg,
                    "total_searches": _search_total,
                })

                for _idx, tag in enumerate(search_tags, 1):
                    _type_label = {
                        "web": "Web Search", "scholar": "Scholar/Academic",
                        "arxiv": "ArXiv", "crossref": "Crossref",
                        "news": "Berita", "wiki": "Wikipedia",
                        "github": "GitHub", "books": "Buku",
                        # Literatur fetcher labels
                        "scopus": "Scopus", "ieee": "IEEE Xplore",
                        "pubmed": "PubMed", "dblp": "DBLP",
                        "dimensions": "Dimensions", "core": "CORE",
                        "doaj": "DOAJ", "plos": "PLOS",
                        "openaire": "OpenAIRE", "europepmc": "Europe PMC",
                        "sinta": "SINTA", "zenodo": "Zenodo",
                        "datacite": "DataCite", "sciencedirect": "ScienceDirect",
                        "openalex": "OpenAlex", "semantic_scholar": "Semantic Scholar",
                        "crossref_publishers": "Publishers (Springer/Wiley/Emerald/SSRN)",
                    }.get(tag["type"], tag["type"])

                    # Send "searching" event with progress counter
                    yield _sse("search_started", {
                        "icon": "🔍",
                        "type": tag["type"],
                        "label": _type_label,
                        "query": tag["query"],
                        "progress": f"{_idx}/{_search_total}",
                        "message": f"🔍 [{_idx}/{_search_total}] {_type_label}: \"{tag['query']}\"",
                    })

                    # Execute the search
                    result_data = execute_tag_search(tag, limit=_fetch_limit)

                    # Count results
                    _n = len(result_data.get("results", [])) if result_data.get("success") else 0
                    _running_count += _n

                    # Send results to frontend with summary
                    frontend_event = format_search_event_for_frontend(tag, result_data)
                    frontend_event["progress"] = f"{_idx}/{_search_total}"
                    frontend_event["running_total"] = _running_count
                    frontend_event["message"] = (
                        f"✅ [{_idx}/{_search_total}] {_type_label}: "
                        f"{_n} hasil ditemukan" +
                        (f" — total {_running_count} hasil" if _idx == _search_total else "")
                    )
                    yield _sse("search_complete", frontend_event)

                    all_search_results.append({
                        "type": tag["type"],
                        "query": tag["query"],
                        "data": result_data,
                    })

                # Format results for AI phase 2
                search_results_context = format_search_results_for_ai(all_search_results)

                # Cap search context to prevent AI overflow (max ~15K chars)
                _MAX_SEARCH_CTX = 15000
                if len(search_results_context) > _MAX_SEARCH_CTX:
                    log.warning("Search context too large (%d chars), truncating to %d",
                                len(search_results_context), _MAX_SEARCH_CTX)
                    search_results_context = search_results_context[:_MAX_SEARCH_CTX] + \
                        "\n\n...(hasil dipotong karena terlalu banyak)..."

                # Log search summary
                _total_results = sum(
                    len(r["data"].get("results", []))
                    for r in all_search_results
                    if r["data"].get("success")
                )
                log.info("Phase 1.5 done: %d searches, %d total results, context=%d chars for conv=%s",
                         len(all_search_results), _total_results,
                         len(search_results_context), conv_id)

                yield _sse("search_phase_end", {
                    "message": f"Menyusun jawaban dari {_total_results} hasil pencarian...",
                    "total_results": _total_results,
                    "search_count": len(all_search_results),
                })

                # Signal composing phase to frontend
                yield _sse("composing_start", {})

                # ── RESET for Phase 2 ──
                # Phase 1 text was only a scaffold (search tags + intro).
                # The REAL answer comes from Phase 2, so we start fresh.
                assistant_content = ""
                phase1_thinking_saved = thinking_content  # keep Phase 1 thinking for context
                thinking_content = ""
                _token_count = 0
                # Clear Phase 1 text from frontend before Phase 2 streams
                yield _sse("replace_text", {"content": ""})

                # Determine target reference count for Phase 2 instructions
                _target_n = _requested_count if _requested_count > 0 else 20
                _target_label = f"TEPAT {_target_n}" if _requested_count > 0 else "minimal 20"

                # ── PHASE 2: AI synthesizes final answer with search data ──
                # Language-aware instruction for Phase 2
                _p2_lang_text = (
                    "Respond in English." if resolved_lang == "en"
                    else "Jawab dalam Bahasa Indonesia."
                )
                _p2_lang_rule = (
                    "Respond in English regardless of the user's message language." if resolved_lang == "en"
                    else "Jawab dalam Bahasa Indonesia apapun bahasa pesan user."
                )
                _phase2_instruction = (
                    "\n\n## ⚠️ INSTRUKSI WAJIB — IKUTI ATAU GAGAL\n"
                    "Pencarian sudah selesai. Hasil pencarian ada di atas dalam format:\n"
                    "  N. **Title**\n     Authors: ... (Year)\n     DOI: ...\n     URL: ...\n\n"
                    "Tugas Anda: rangkum hasil pencarian di atas menjadi jawaban final.\n\n"
                    "ATURAN MUTLAK (jika dilanggar = jawaban ditolak):\n"
                    "1. HANYA gunakan referensi dari hasil pencarian di atas. DILARANG mengarang.\n"
                    "2. Setiap referensi yang Anda sebutkan WAJIB menyertakan link yang bisa diklik.\n"
                    "   Format: [Author et al. (Year) - Title](URL atau https://doi.org/DOI)\n"
                    "   Contoh: [Tieman (2011) - Halal Supply Chain](https://doi.org/10.1108/17590831111129721)\n"
                    "3. JANGAN tulis referensi tanpa link. Setiap entri HARUS punya hyperlink.\n"
                    "4. JANGAN ulangi pertanyaan user.\n"
                    "5. JANGAN generate tag pencarian baru ([WEBSEARCH:], [SCHOLAR:], dll).\n"
                    "6. Langsung berikan daftar referensi terstruktur dengan link.\n"
                    f"7. BAHASA: {_p2_lang_rule}\n"
                    f"8. USER MEMINTA {_target_n} REFERENSI. Anda WAJIB memberikan {_target_label} referensi.\n"
                    "   Jika user minta 50, berikan 50. Jika user minta 20, berikan 20.\n"
                    "   Jika hasil pencarian kurang dari yang diminta, tampilkan SEMUA yang ada.\n"
                    "9. Pilih referensi yang PALING RELEVAN dengan topik user.\n"
                    "10. Format output:\n"
                    "   ## Hasil Pencarian\n"
                    f"   Berikut {_target_n} referensi yang ditemukan:\n\n"
                    "   1. [Author (Year) - Title](URL)\n"
                    "      Ringkasan singkat...\n\n"
                    "   2. [Author (Year) - Title](URL)\n"
                    "      Ringkasan singkat...\n\n"
                    "   ...(dan seterusnya untuk semua hasil yang relevan)\n"
                )
                # Phase 2 system: base system prompt ONLY (no search data here).
                # Search data goes into a SEPARATE user message to avoid truncation.
                phase2_system = _sys + _phase2_instruction

                messages_phase2 = [{"role": "system", "content": phase2_system}]
                for msg in _history:
                    role = msg.role if msg.role in ("user", "assistant") else "user"
                    messages_phase2.append({"role": role, "content": msg.content})

                # Add search results as a DEDICATED user message so they are never
                # truncated by the system prompt size cap.  Then add the explicit
                # instruction to summarise with clickable links.
                messages_phase2.append({
                    "role": "user",
                    "content": (
                        "Berikut adalah hasil pencarian REAL dari multiple fetcher:\n\n"
                        + search_results_context
                        + "\n\n---\n\n"
                        f"Rangkum hasil pencarian di atas menjadi jawaban final.\n\n"
                        "ATURAN WAJIB:\n"
                        "1. HANYA gunakan referensi dari hasil pencarian di atas. DILARANG mengarang.\n"
                        "2. Setiap referensi WAJIB berformat markdown link: [Author (Year) - Title](URL)\n"
                        "3. Gunakan URL dari field URL/DOI di hasil pencarian.\n"
                        f"4. User meminta {_target_n} referensi. Tampilkan {_target_label} referensi dengan link.\n"
                        "5. Pilih yang PALING RELEVAN dengan topik. Jika kurang dari yang diminta, tampilkan semua yang ada.\n"
                        "5. Berikan ringkasan singkat untuk tiap referensi.\n"
                        "6. JANGAN tulis referensi tanpa link.\n"
                    ),
                })

                _phase = 2
                response_p2, model_used = route_chat_call(
                    json={
                        "messages": messages_phase2,
                        "stream": True,
                        "max_tokens": 65536,
                        "reasoning": {"effort": "medium"},
                    },
                    stream=True,
                    timeout=1800,
                )

                _phase2_stream_ok = True
                try:
                    for line in response_p2.iter_lines():
                        if not line:
                            continue
                        if isinstance(line, bytes):
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
                            assistant_content += text
                            _token_count += 1
                            yield _sse("text", {"content": text})
                            # Throttle: only update Redis every 20 tokens (bug 1)
                            # Check cancel BEFORE writing stream state (bug 2)
                            if _token_count % 20 == 0:
                                if _r:
                                    try:
                                        _cancel_raw = _r.get(_cancel_key(conv_id))
                                        if _cancel_raw == my_stream_id:
                                            # Cancel detected: mark cancelled in Redis (bug 4),
                                            # save partial message (bug 3), yield done, return
                                            stream_state["status"] = "cancelled"
                                            try:
                                                _r.setex(_stream_key(conv_id), 60, json.dumps(stream_state))
                                            except Exception:
                                                pass
                                            _persist_chat_final(
                                                assistant_content,
                                                phase1_thinking_saved + "\n\n--- Phase 2 ---\n\n" + thinking_content,
                                            )
                                            yield _sse("done", {"message_id": None, "cancelled": True})
                                            return
                                    except (json.JSONDecodeError, KeyError):
                                        pass
                                stream_state["content"] = assistant_content
                                try:
                                    if _r:
                                        _r.setex(_stream_key(conv_id), 1800, json.dumps(stream_state))
                                except Exception:
                                    pass
                        thinking_raw = (
                            delta.get("thinking")
                            or delta.get("reasoning_content")
                            or delta.get("reasoning")
                            or delta.get("thinking_content")
                        )
                        if thinking_raw:
                            if isinstance(thinking_raw, dict):
                                thinking_raw = thinking_raw.get("content", "")
                            if thinking_raw:
                                thinking_content += thinking_raw
                                yield _sse("thinking", {"content": thinking_raw})
                                # Update Redis state (throttle: every 20 chunks)
                                _token_count += 1
                                if _token_count % 20 == 0:
                                    # Combine Phase 1 + Phase 2 thinking (bug 5)
                                    stream_state["thinking"] = phase1_thinking_saved + "\n\n--- Phase 2 ---\n\n" + thinking_content
                                    try:
                                        if _r:
                                            _r.setex(_stream_key(conv_id), 1800, json.dumps(stream_state))
                                    except Exception:
                                        pass
                except (_requests.exceptions.ChunkedEncodingError, _urllib3.exceptions.ProtocolError) as _stream_err:
                    _phase2_stream_ok = False
                    log.warning("Phase 2 stream ended prematurely conv=%s: %s — using partial content (%d chars)",
                               conv_id, _stream_err, len(assistant_content))
                    # No re-yield needed — Phase 2 already streamed tokens to user progressively

            # Log Phase 2 completion (or Phase 1 if no search tags)
            if _phase == 2:
                log.info("Phase 2 done: content=%d chars, thinking=%d chars for conv=%s",
                         len(assistant_content), len(thinking_content), conv_id)
                log.info("Phase 2 content preview: %s", assistant_content[:200])

            # Combine Phase 1 + Phase 2 thinking for persistence
            try:
                _combined_thinking = phase1_thinking_saved + "\n\n--- Phase 2 ---\n\n" + thinking_content
            except NameError:
                _combined_thinking = thinking_content

            # Save thinking to filesystem if any
            if _combined_thinking and conv.paper_id:
                try:
                    save_thinking_to_fs(
                        username=username,
                        paper_id=conv.paper_id,
                        conv_id=conv_id,
                        thinking_text=_combined_thinking,
                        message_id="pending",
                    )
                except Exception as e:
                    log.warning("Failed to save thinking: %s", e)

            # ── FALLBACK: If content empty but thinking has text, retry ──
            if not assistant_content.strip() and _combined_thinking.strip():
                log.warning(
                    "Chat returned empty content with %d chars thinking — "
                    "making fallback call for conv=%s",
                    len(_combined_thinking), conv_id,
                )
                yield _sse("composing_start", {})
                try:
                    _fb_lang = "English" if resolved_lang == "en" else "Bahasa Indonesia"
                    fallback_messages = [
                        {"role": "system", "content": (
                            "You are a concise academic writing assistant. "
                            f"Based on the reasoning below, produce a direct, helpful response "
                            f"in {_fb_lang}. "
                            "Output ONLY the final answer — no thinking, no tags."
                        )},
                        {"role": "user", "content": _combined_thinking[-4000:]},
                    ]
                    fb_resp, _ = route_chat_call(
                        json={"messages": fallback_messages, "stream": False, "max_tokens": 65536},
                        stream=False,
                        timeout=1800,
                    )
                    fb_choices = fb_resp.json().get("choices", [])
                    if fb_choices:
                        fb_content = (
                            fb_choices[0].get("message", {}).get("content", "")
                            or fb_choices[0].get("delta", {}).get("content", "")
                        ).strip()
                        if fb_content:
                            assistant_content = fb_content
                            # Mirror the normal replay: persist progressively to
                            # Redis so a refresh mid-replay resumes from the live
                            # position instead of showing nothing until completion.
                            stream_state["content"] = ""
                            for _i in range(0, len(assistant_content), 8):
                                yield _sse("text", {"content": assistant_content[_i:_i + 8]})
                                _token_count += 1
                                if _token_count % 20 == 0:
                                    stream_state["content"] = assistant_content[:_i + 8]
                                    if _r:
                                        try:
                                            _r.setex(_stream_key(conv_id), 1800, json.dumps(stream_state))
                                        except Exception:
                                            pass
                            stream_state["content"] = assistant_content
                            if _r:
                                try:
                                    _r.setex(_stream_key(conv_id), 1800, json.dumps(stream_state))
                                except Exception:
                                    pass
                except Exception as e:
                    log.warning("Fallback chat call failed: %s", e)

                # Last resort: if still empty, extract last sentence of thinking
                if not assistant_content.strip():
                    lines = _combined_thinking.rstrip().split("\n")
                    meaningful = [l for l in lines if l.strip() and not l.strip().startswith(("#", "//", "/*", "*"))][-5:]
                    if meaningful:
                        assistant_content = "\n".join(meaningful)[:2000]
                        log.info("Fallback: using last meaningful lines from thinking (%d chars)", len(assistant_content))
                        yield _sse("replace_text", {"content": assistant_content})

            # ── ULTIMATE FALLBACK: If still empty and we have search results,
            # format them directly as the response ──
            if not assistant_content.strip() and search_tags:
                log.warning("All fallbacks exhausted — using raw search results for conv=%s", conv_id)
                _fallback_parts = [
                    "## 🔍 Hasil Pencarian\n\n",
                    "AI belum berhasil menyusun jawaban, berikut hasil pencarian langsung:\n\n",
                ]
                try:
                    _fallback_parts.append(search_results_context)
                except NameError:
                    _fallback_parts.append("(Data pencarian tidak tersedia)")
                assistant_content = "".join(_fallback_parts)
                stream_state["content"] = ""
                for _i in range(0, len(assistant_content), 8):
                    yield _sse("text", {"content": assistant_content[_i:_i + 8]})
                stream_state["content"] = assistant_content
                if _r:
                    try:
                        _r.setex(_stream_key(conv_id), 1800, json.dumps(stream_state))
                    except Exception:
                        pass

            # ── Finalize: parse ops, apply to paper, save to DB/FS, mark Redis.
            # Done in a NON-yielding helper so the same path runs whether the
            # client is still connected OR disconnected mid-stream (see the
            # GeneratorExit handler below). Guarded to run exactly once.
            _fin = _persist_chat_final(assistant_content, _combined_thinking)

            if _fin.get("paper_applied"):
                yield _sse("paper_applied", {
                    "operations": _fin["paper_applied"].get("operations"),
                    "results": _fin["paper_applied"].get("results"),
                    "errors": _fin["paper_applied"].get("errors"),
                })
                yield _sse("replace_text", {"content": _fin["content"]})

            if _fin.get("ask_user"):
                yield _sse("ask_user", _fin["ask_user"])
                yield _sse("replace_text", {"content": _fin["content"]})

            # Emit docx_ready event with download URL
            if _fin.get("docx_url"):
                yield _sse("docx_ready", {
                    "url": _fin["docx_url"],
                    "filename": _fin["docx_filename"],
                })

            if _fin.get("message_id"):
                done_data = {"message_id": _fin["message_id"]}
                if _fin.get("docx_url"):
                    done_data["file_url"] = _fin["docx_url"]
                    done_data["file_name"] = _fin["docx_filename"]
                yield _sse("done", done_data)
            elif _fin.get("empty"):
                yield _sse("error", {"message": "AI returned an empty response."})
            else:
                yield _sse("error", {"message": "Gagal menyimpan pesan ke database."})

        except GeneratorExit:
            # ── Client disconnected / frontend errored mid-stream ─────────
            # The browser closed the SSE connection (refresh, navigation, JS
            # error, network drop). We MUST still finish: drain the remaining
            # AI tokens off the open upstream stream and persist the completion
            # so it is never lost. No yields allowed here (socket is gone).
            log.info("Client disconnected mid-stream for conv=%s — finishing in background", conv_id)
            try:
                _drain_remaining()
            except Exception:
                log.exception("Background finalize after disconnect failed for conv=%s", conv_id)
            raise

        except Exception as e:
            log.exception("Error in AI call: %s", e)
            try:
                db.session.rollback()
            except Exception as rb_err:
                log.warning("Rollback failed: %s", rb_err)
            # Save partial assistant message on error (bug 3)
            try:
                _combined = phase1_thinking_saved + "\n\n--- Phase 2 ---\n\n" + thinking_content
            except NameError:
                _combined = thinking_content
            _persist_chat_final(assistant_content, _combined)
            # Mark stream as error in Redis
            stream_state["status"] = "error"
            stream_state["error"] = "Terjadi kesalahan pada server"
            try:
                if _r:
                    _r.setex(_stream_key(conv_id), 60, json.dumps(stream_state))
            except Exception:
                pass
            err_str = str(e)
            if any(kw in err_str.lower() for kw in ("401", "403", "api key", "unauthorized")):
                msg = "API key tidak valid atau sudah expired. Hubungi admin untuk memperbarui konfigurasi API."
            elif any(kw in err_str.lower() for kw in ("429", "rate limit", "too many")):
                msg = "Terlalu banyak request ke AI. Tunggu beberapa saat lalu coba lagi."
            elif any(kw in err_str.lower() for kw in ("timeout", "timed out")):
                msg = "AI terlalu lama merespons. Coba lagi atau sederhanakan permintaan Anda."
            elif any(kw in err_str.lower() for kw in ("connection", "network", "dns", "socket")):
                msg = "Koneksi ke server AI terputus. Periksa koneksi internet Anda dan coba lagi."
            elif any(kw in err_str.lower() for kw in ("500", "502", "503", "504", "server error")):
                msg = "Server AI sedang mengalami gangguan. Coba lagi dalam beberapa saat."
            elif any(kw in err_str.lower() for kw in ("404", "not found", "model")):
                msg = "Model AI tidak tersedia. Hubungi admin untuk memeriksa konfigurasi model."
            else:
                msg = "AI belum berhasil merespons. Coba lagi atau ubah permintaan Anda."
            yield _sse("error", {"message": msg})
            yield _sse("done", {"message_id": None, "error": msg})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@simple_chat.route("/api/chat/conversations/<conv_id>/stream-status", methods=["GET"])
@jwt_required()
def get_stream_status(conv_id: str):
    """Check if a conversation has an active streaming session.
    
    Returns:
        - status: 'streaming', 'done', 'error', or 'not_found'
        - content: last saved content (if streaming/done)
        - thinking: last saved thinking (if streaming/done)
        - error: error message (if error)
        - message_id: ID of saved message (if done)
    """
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Invalid user"}), 401

    # Verify conversation ownership
    conv = Conversation.query.filter_by(id=conv_id, user_id=user_id).first()
    if not conv:
        return jsonify({"status": "not_found"}), 404

    try:
        _r = get_redis()
        raw = _r.get(_stream_key(conv_id)) if _r else None
        if not raw:
            return jsonify({"status": "not_found"})
        
        state = json.loads(raw)
        return jsonify({
            "status": state.get("status", "not_found"),
            "content": state.get("content", ""),
            "thinking": state.get("thinking", ""),
            "error": state.get("error"),
            "message_id": state.get("message_id"),
            "started_at": state.get("started_at"),
        })
    except Exception as e:
        log.warning("Failed to get stream status: %s", e)
        return jsonify({"status": "not_found"})


@simple_chat.route("/api/chat/conversations/<conv_id>/cancel-stream", methods=["POST"])
@jwt_required()
def cancel_stream(conv_id: str):
    """Cancel an active streaming session.
    
    Sets the cancel flag in a separate Redis key (never overwritten by the
    streaming generator) so the backend can reliably detect cancellation.
    Also marks the stream state as 'cancelled' for frontend polling.
    """
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Invalid user"}), 401

    # Verify conversation ownership
    conv = Conversation.query.filter_by(id=conv_id, user_id=user_id).first()
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404

    try:
        _r = get_redis()
        if not _r:
            return jsonify({"error": "Redis unavailable"}), 500

        raw = _r.get(_stream_key(conv_id))
        if not raw:
            return jsonify({"status": "not_found", "message": "No active stream"})
        
        state = json.loads(raw)
        if state.get("status") != "streaming":
            return jsonify({"status": state.get("status"), "message": "Stream not active"})
        
        # Mark as cancelled in BOTH keys:
        # - stream key for frontend polling
        # - cancel key for generator to detect (never overwritten by generator writes)
        state["status"] = "cancelled"
        state["cancelled_at"] = datetime.now(timezone.utc).isoformat()
        _r.setex(_stream_key(conv_id), 60, json.dumps(state))
        _r.setex(_cancel_key(conv_id), 60, state.get("stream_id", ""))
        
        return jsonify({"status": "cancelled", "message": "Stream cancelled successfully"})
    except Exception as e:
        log.warning("Failed to cancel stream: %s", e)
        return jsonify({"error": "Failed to cancel stream"}), 500


# ── FAQ Analytics ────────────────────────────────────────────────────────────
@simple_chat.route("/api/chat/faq", methods=["GET"])
@jwt_required()
def get_faq_analytics():
    """Return top user questions asked to AI, grouped by normalized content.

    Query params:
        paper_id: optional — scope to a specific paper
        period:   'day' | 'week' | 'month' | 'all' (default: month)
        limit:    max items to return (default: 20)

    Returns:
        {
            "faq": [
                { "question": "...", "count": N },
                ...
            ],
            "period": "...",
            "total_messages": N
        }
    """
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Invalid user"}), 401

    paper_id = request.args.get("paper_id")
    period = request.args.get("period", "month")
    try:
        limit = min(int(request.args.get("limit", 20)), 50)
    except (ValueError, TypeError):
        limit = 20

    from sqlalchemy import func, text

    # Date filter
    now = datetime.now(timezone.utc)
    period_map = {
        "day": now - timedelta(days=1),
        "week": now - timedelta(days=7),
        "month": now - timedelta(days=30),
    }
    since = period_map.get(period)

    q = (
        db.session.query(
            ChatMessage.content,
            func.count(ChatMessage.id).label("cnt"),
        )
        .join(Conversation, ChatMessage.conversation_id == Conversation.id)
        .filter(ChatMessage.role == "user")
        .filter(ChatMessage.content.isnot(None))
        .filter(ChatMessage.content != "")
    )

    if paper_id:
        q = q.filter(Conversation.paper_id == paper_id)
    if since:
        q = q.filter(ChatMessage.created_at >= since)

    q = q.group_by(ChatMessage.content).order_by(text("cnt DESC")).limit(limit)
    rows = q.all()

    # Total user messages in period
    total_q = (
        db.session.query(func.count(ChatMessage.id))
        .join(Conversation, ChatMessage.conversation_id == Conversation.id)
        .filter(ChatMessage.role == "user")
    )
    if paper_id:
        total_q = total_q.filter(Conversation.paper_id == paper_id)
    if since:
        total_q = total_q.filter(ChatMessage.created_at >= since)
    total_messages = total_q.scalar() or 0

    faq = [{"question": r.content.strip(), "count": r.cnt} for r in rows if r.content]

    return jsonify({
        "faq": faq,
        "period": period,
        "total_messages": total_messages,
    })


# ── Chat DOCX File Serving ─────────────────────────────────────────────────

@simple_chat.route("/api/chat/conversations/<conv_id>/files/<filename>", methods=["GET"])
@jwt_required()
def serve_chat_docx_file(conv_id: str, filename: str):
    """Serve a generated chat DOCX file."""
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Invalid user"}), 401

    # Verify conversation ownership
    conv = Conversation.query.filter_by(id=conv_id, user_id=user_id).first()
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404

    # Security: prevent path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        return jsonify({"error": "Invalid filename"}), 400

    # Build file path
    try:
        from utils.core.user_storage import get_username as _get_uname
        uname = _get_uname(user_id=user_id)
    except Exception:
        uname = f"user_{user_id}"

    base = Path(__file__).resolve().parent.parent.parent / "user" / uname
    chat_docs_dir = base / (conv.paper_id or "global") / "chat_docs" / conv_id
    file_path = chat_docs_dir / filename

    if not file_path.exists():
        return jsonify({"error": "File not found"}), 404

    download_name = filename
    return send_file(
        str(file_path),
        as_attachment=True,
        download_name=download_name,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@simple_chat.route("/api/chat/conversations/<conv_id>/generate-docx", methods=["POST"])
@jwt_required()
def generate_chat_docx(conv_id: str):
    """Generate a DOCX file from a JSON spec, save it, and return download URL.

    Request body: the full JSON spec (same format as [GENERATE_DOCX] tag content).
    Returns: {"url": "/api/chat/.../files/...", "filename": "..."}
    """
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Invalid user"}), 401

    conv = Conversation.query.filter_by(id=conv_id, user_id=user_id).first()
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404

    spec = request.get_json(silent=True)
    if not spec or not isinstance(spec, dict):
        return jsonify({"error": "Invalid JSON spec"}), 400

    try:
        from tools.chat.docx_renderer import render_docx
        from pathlib import Path as _Path

        safe_title = re.sub(r'[^a-zA-Z0-9_\-]+', '_', str(spec.get("title", "document"))).strip("_")[:60] or "document"
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        docx_filename = f"{safe_title}_{ts}.docx"

        try:
            from utils.core.user_storage import get_username as _get_uname
            uname = _get_uname(user_id=user_id)
        except Exception:
            uname = f"user_{user_id}"

        base = Path(__file__).resolve().parent.parent.parent / "user" / uname
        chat_docs_dir = base / (conv.paper_id or "global") / "chat_docs" / conv_id
        chat_docs_dir.mkdir(parents=True, exist_ok=True)
        docx_path = chat_docs_dir / docx_filename

        render_docx(spec, docx_path)
        docx_url = f"/api/chat/conversations/{conv_id}/files/{docx_filename}"

        return jsonify({
            "url": docx_url,
            "filename": docx_filename,
            "size": docx_path.stat().st_size,
        })
    except Exception as e:
        log.exception("generate_chat_docx failed")
        return jsonify({"error": "Internal server error"}), 500
