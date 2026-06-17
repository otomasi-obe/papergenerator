"""
Simple streaming chat — no tools, no memory, no workflow.
User message → inject paper data as context → call AI → stream SSE → save message.
Supports [APPLY_PAPER] tags for direct paper editing from chat.
"""

import json
import logging
import os
import re
import threading
import uuid
from datetime import datetime, timezone, timedelta

import redis
from flask import Blueprint, Response, request, stream_with_context, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required

from sqlalchemy import desc

from database.models import ChatMessage, Conversation, Paper, db, safe_commit
from utils.ai_tools.model_router import route_chat_call
from utils.core.user_storage import get_username, save_chat_send_by_id, save_chat_recv_by_id
from tools.chat.tools import parse_completion, apply_operations, save_thinking_to_fs
from tools.Literatur.slr_api import get_pinned_literature

log = logging.getLogger(__name__)

simple_chat = Blueprint("simple_chat", __name__)

# Redis connection for streaming state
_REDIS = None
_REDIS_LOCK = threading.Lock()


def get_redis():
    global _REDIS
    if _REDIS is None:
        with _REDIS_LOCK:
            if _REDIS is None:
                try:
                    _REDIS = redis.Redis.from_url(
                        os.getenv("REDIS_URL", "redis://localhost:6379/0"),
                        decode_responses=True,
                    )
                except Exception:
                    return None
    # Health check: if connection went stale (Redis restart etc.), reconnect
    try:
        _REDIS.ping()
    except Exception:
        with _REDIS_LOCK:
            try:
                _REDIS.close()
            except Exception:
                pass
            _REDIS = None
        return get_redis()
    return _REDIS


def _stream_key(conv_id: str) -> str:
    """Redis key for streaming state."""
    return f"chat:stream:{conv_id}"


def _gen_id():
    return uuid.uuid4().hex[:16]


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

    data = paper.data if isinstance(paper.data, dict) else {}
    if not data:
        return f"Paper: {paper.title or 'Untitled'}\nPaper ID: {paper_id}\n(Paper data is empty — belum ada konten.)"

    # Always include paper_id in the context for [APPLY_PAPER] operations
    data["_paper_id"] = paper_id

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
            result += "\n// Beberapa konten section dipotong. Gunakan [APPLY_PAPER] untuk membaca/mengedit section lengkap."
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
            result += "\n// Paper context dipotong. Gunakan [APPLY_PAPER] untuk mengedit section di luar konteks yang terlihat."
        return result

    # Step 3: harder trim (1000 chars per text block)
    for sec in d.get("sections", []):
        for block in sec.get("content", []):
            if isinstance(block, dict) and block.get("text") and len(block["text"]) > 1000:
                block["text"] = block["text"][:1000] + "... [dipotong]"

    result = json.dumps(d, indent=2, ensure_ascii=False)
    result += "\n// [Truncated: sections beyond 80K chars not shown — some content was aggressively trimmed. Use [APPLY_PAPER] to edit specific sections.]"
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
    return jsonify([c.to_dict() for c in convs])


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
    if len(content) > 100000:
        return jsonify({"error": "Message is too long (max 100000 chars)"}), 400
    if len(images) > 5:
        return jsonify({"error": "Maksimal 5 gambar per pesan"}), 400

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
        from database.models import User as UserModel
        current_user = UserModel.query.get(user_id)
        if current_user:
            user_prefs = []
            nickname = current_user.nickname or current_user.name
            if nickname:
                user_prefs.append(f"- Panggil user dengan nama: **{nickname}**")
            institution = current_user.institution or ""
            if institution:
                user_prefs.append(f"- Institusi user: **{institution}**")
            lang = current_user.preferred_language or "id"
            if lang == "en":
                user_prefs.append("- SELALU gunakan Bahasa Inggris (English) untuk respons dan penulisan paper, kecuali user meminta bahasa lain.")
            else:
                user_prefs.append("- Gunakan Bahasa Indonesia sebagai bahasa utama untuk respons dan penulisan paper.")
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

    # ── @slr tag: inject pinned literature into system prompt ────────────
    # User ketik @slr di pesan → ambil literatur yang di-pin dan injeksi
    # sebagai reference context. Tag @slr dihapus dari pesan sebelum ke AI
    # HANYA jika literatur berhasil diinjeksi.
    slr_tag_detected = False
    if "@slr" in content.lower():
        slr_tag_detected = True
        if conv.paper_id:
            try:
                pinned_text = get_pinned_literature(conv.paper_id, user_id, max_items=10)
                if pinned_text:
                    system_content += f"## SLR References (Pinned)\n{pinned_text}\n\n"
                    # Only strip @slr if literature was actually injected
                    content = re.sub(r"@slr\b", "", content, flags=re.IGNORECASE).strip()
                    log.info("@slr tag: injected %d pinned literature items for paper=%s", pinned_text.count("\n[") + 1, conv.paper_id)
                else:
                    # No pinned literature — keep @slr so AI sees it, add a note
                    system_content += "## SLR Note\nUser used @slr but no pinned literature found for this paper. Suggest running an SLR search.\n\n"
                    log.info("@slr tag: no pinned literature for paper=%s, keeping tag in message", conv.paper_id)
            except Exception as e:
                log.warning("@slr tag: failed to load pinned literature: %s", e)
        else:
            # No paper_id — strip @slr to avoid confusion
            content = re.sub(r"@slr\b", "", content, flags=re.IGNORECASE).strip()

    # ── @draft tag: inject named chat drafts into system prompt ───────────
    # User writes "@draft <name>" or "@draft name1,name2" → fetch those drafts
    # and inject as context. Tag removed from message before AI call.
    draft_tag_detected = False
    if conv.paper_id:
        # BUG-23: Limit input before regex to prevent ReDoS (max 500 chars)
        _draft_search_input = content[:500]
        # Match "@draft name" or "@draft name1,name2" (comma-separated names)
        draft_match = re.search(r"@draft\s+([^\s@]+(?:\s*,\s*[^\s@]+)*)", _draft_search_input, flags=re.IGNORECASE)
        if draft_match:
            draft_tag_detected = True
            raw_names = draft_match.group(1)
            # Split by comma, strip, filter empty
            names = [n.strip() for n in raw_names.split(",") if n.strip()]
            # Remove the whole "@draft ..." from user content
            content = content[: draft_match.start()].strip() + " " + content[draft_match.end():].strip()
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

    def generate():
        assistant_content = ""
        thinking_content = ""
        model_used = ""
        _token_count = 0
        _r = get_redis()
        log.info("Chat generate started for conv_id=%s", conv_id)

        # Save streaming state to Redis (for reconnect after refresh)
        stream_state = {
            "status": "streaming",
            "conv_id": conv_id,
            "content": "",
            "thinking": "",
            "started_at": datetime.now(timezone.utc).isoformat(),
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
                   "paper_applied": None, "ask_user": None, "empty": False}
            if _finalized:
                return out
            _finalized = True
            try:
                parsed = parse_completion(final_content or "")
                content = final_content or ""
                if parsed["has_operations"] and conv.paper_id:
                    try:
                        result = apply_operations(conv.paper_id, parsed["operations"])
                        out["paper_applied"] = {
                            "operations": parsed["operations"],
                            "results": result.get("results"),
                            "errors": result.get("errors"),
                        }
                    except Exception:
                        log.exception("apply_operations failed during finalize")
                    content = parsed["cleaned_text"] or content
                if parsed["has_ask_user"] and parsed["ask_user"]:
                    out["ask_user"] = parsed["ask_user"]
                    if parsed["cleaned_text"]:
                        content = parsed["cleaned_text"]
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
                            db.session.commit()
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
            # Build message list: system + history + current user message
            messages_phase1 = [{"role": "system", "content": system_content}]

            # Include recent history (last 20 messages)
            history = (
                ChatMessage.query.filter_by(conversation_id=conv.id)
                .order_by(ChatMessage.created_at.desc())
                .limit(20)
                .all()
            )
            history.reverse()
            for msg in history:
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
                    "max_tokens": 8192,
                },
                stream=True,
                timeout=900,
            )

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

            # Signal end of thinking phase (before content starts)
            if phase1_thinking:
                yield _sse("thinking_done", {})
                thinking_content = phase1_thinking

            # ── Check for search tags in phase 1 response ─────────────
            search_tags = []
            try:
                from tools.chat.search_tools import extract_search_tags
                search_tags = extract_search_tags(phase1_text)
            except Exception as e:
                log.warning("Failed to extract search tags: %s", e)

            # ── If no search tags → single-phase: stream phase 1 directly ─
            if not search_tags:
                # Signal composing phase, then stream text in chunks
                assistant_content = phase1_text
                yield _sse("composing_start", {})
                import time as _time
                _time.sleep(0.3)  # Brief pause so "Menyusun jawaban..." is visible

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
                    _time.sleep(0.01)  # Tiny delay for smooth streaming feel
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
                            # Check cancel using the same fetch cadence
                            try:
                                _raw = _r.get(_stream_key(conv_id))
                                if _raw:
                                    _st = json.loads(_raw)
                                    if _st.get("status") == "cancelled":
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

            else:
                # ── PHASE 1.5: Execute searches with real-time progress ──
                log.info("Search tags found: %d — executing for conv=%s", len(search_tags), conv_id)

                # Thinking already streamed above during phase 1 loop

                from tools.chat.search_tools import (
                    execute_tag_search,
                    format_search_event_for_frontend,
                    format_search_results_for_ai,
                )

                all_search_results = []
                yield _sse("search_phase_start", {"message": "Mencari referensi..."})

                for tag in search_tags:
                    # Send "searching" event to frontend
                    yield _sse("search_started", {
                        "icon": "🔍",
                        "type": tag["type"],
                        "query": tag["query"],
                    })

                    # Execute the search
                    result_data = execute_tag_search(tag)

                    # Send results to frontend
                    frontend_event = format_search_event_for_frontend(tag, result_data)
                    yield _sse("search_complete", frontend_event)

                    all_search_results.append({
                        "type": tag["type"],
                        "query": tag["query"],
                        "data": result_data,
                    })

                # Format results for AI phase 2
                search_results_context = format_search_results_for_ai(all_search_results)
                yield _sse("search_phase_end", {"message": "Menyusun jawaban..."})

                # Signal composing phase to frontend
                yield _sse("composing_start", {})

                # ── PHASE 2: AI synthesizes final answer with search data ──
                phase2_system = system_content + "\n\n" + search_results_context

                messages_phase2 = [{"role": "system", "content": phase2_system}]
                for msg in history:
                    role = msg.role if msg.role in ("user", "assistant") else "user"
                    messages_phase2.append({"role": role, "content": msg.content})

                # Add phase 1 response as assistant context so AI knows what it "thought"
                # (but strip search tags — user never sees them)
                from tools.chat.search_tools import strip_search_tags
                phase1_clean = strip_search_tags(phase1_text).strip()
                if phase1_clean:
                    messages_phase2.append({"role": "assistant", "content": phase1_clean})

                _phase = 2
                response_p2, model_used = route_chat_call(
                    json={
                        "messages": messages_phase2,
                        "stream": True,
                        "max_tokens": 8192,
                    },
                    stream=True,
                    timeout=900,
                )

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
                        # Update Redis state (batch updates, not every chunk)
                        stream_state["content"] = assistant_content
                        try:
                            if _r:
                                _r.setex(_stream_key(conv_id), 1800, json.dumps(stream_state))
                        except Exception:
                            pass
                        # Check cancel every ~20 tokens
                        if _token_count % 20 == 0 and _r:
                            try:
                                _raw = _r.get(_stream_key(conv_id))
                                if _raw:
                                    _st = json.loads(_raw)
                                    if _st.get("status") == "cancelled":
                                        yield _sse("done", {"message_id": None, "cancelled": True})
                                        return
                            except (json.JSONDecodeError, KeyError):
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
                                stream_state["thinking"] = thinking_content
                                try:
                                    if _r:
                                        _r.setex(_stream_key(conv_id), 1800, json.dumps(stream_state))
                                except Exception:
                                    pass

            # Save thinking to filesystem if any
            if thinking_content and conv.paper_id:
                try:
                    save_thinking_to_fs(
                        username=username,
                        paper_id=conv.paper_id,
                        conv_id=conv_id,
                        thinking_text=thinking_content,
                        message_id="pending",
                    )
                except Exception as e:
                    log.warning("Failed to save thinking: %s", e)

            # ── FALLBACK: If content empty but thinking has text, retry ──
            if not assistant_content.strip() and thinking_content.strip():
                log.warning(
                    "Chat returned empty content with %d chars thinking — "
                    "making fallback call for conv=%s",
                    len(thinking_content), conv_id,
                )
                yield _sse("composing_start", {})
                try:
                    fallback_messages = [
                        {"role": "system", "content": (
                            "You are a concise academic writing assistant. "
                            "Based on the reasoning below, produce a direct, helpful response "
                            "in the same language the user is using. "
                            "Output ONLY the final answer — no thinking, no tags."
                        )},
                        {"role": "user", "content": thinking_content[-4000:]},
                    ]
                    fb_resp, _ = route_chat_call(
                        json={"messages": fallback_messages, "stream": False, "max_tokens": 4096},
                        stream=False,
                        timeout=120,
                    )
                    fb_choices = fb_resp.json().get("choices", [])
                    if fb_choices:
                        fb_content = (
                            fb_choices[0].get("message", {}).get("content", "")
                            or fb_choices[0].get("delta", {}).get("content", "")
                        ).strip()
                        if fb_content:
                            assistant_content = fb_content
                            import time as _time
                            _time.sleep(0.2)
                            # Mirror the normal replay: persist progressively to
                            # Redis so a refresh mid-replay resumes from the live
                            # position instead of showing nothing until completion.
                            stream_state["content"] = ""
                            for _i in range(0, len(assistant_content), 8):
                                yield _sse("text", {"content": assistant_content[_i:_i + 8]})
                                _time.sleep(0.01)
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
                    lines = thinking_content.rstrip().split("\n")
                    meaningful = [l for l in lines if l.strip() and not l.strip().startswith(("#", "//", "/*", "*"))][-5:]
                    if meaningful:
                        assistant_content = "\n".join(meaningful)[:2000]
                        log.info("Fallback: using last meaningful lines from thinking (%d chars)", len(assistant_content))
                        yield _sse("replace_text", {"content": assistant_content})

            # ── Finalize: parse ops, apply to paper, save to DB/FS, mark Redis.
            # Done in a NON-yielding helper so the same path runs whether the
            # client is still connected OR disconnected mid-stream (see the
            # GeneratorExit handler below). Guarded to run exactly once.
            _fin = _persist_chat_final(assistant_content, thinking_content)

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

            if _fin.get("message_id"):
                yield _sse("done", {"message_id": _fin["message_id"]})
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
            # Mark stream as error in Redis
            stream_state["status"] = "error"
            stream_state["error"] = str(e)[:200]
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
    
    Marks the stream as 'cancelled' in Redis so the backend knows to stop.
    The actual cancellation happens when the streaming generator checks the flag.
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
        raw = _r.get(_stream_key(conv_id)) if _r else None
        if not raw:
            return jsonify({"status": "not_found", "message": "No active stream"})
        
        state = json.loads(raw)
        if state.get("status") != "streaming":
            return jsonify({"status": state.get("status"), "message": "Stream not active"})
        
        # Mark as cancelled
        state["status"] = "cancelled"
        state["cancelled_at"] = datetime.now(timezone.utc).isoformat()
        if _r:
            _r.setex(_stream_key(conv_id), 60, json.dumps(state))
        
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
