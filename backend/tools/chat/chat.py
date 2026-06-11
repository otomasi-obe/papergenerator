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
from datetime import datetime, timezone

import redis
from flask import Blueprint, Response, request, stream_with_context, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required

from sqlalchemy import desc

from database.models import ChatMessage, Conversation, Paper, db
from utils.ai_tools.model_router import route_chat_call
from utils.core.user_storage import get_username, save_chat_send_by_id, save_chat_recv_by_id
from tools.chat.tools import parse_completion, apply_operations, save_thinking_to_fs
from tools.Literatur.slr_api import get_pinned_literature

log = logging.getLogger(__name__)

simple_chat = Blueprint("simple_chat", __name__)

# Redis connection for streaming state
_REDIS = redis.Redis.from_url(
    os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    decode_responses=True,
)


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
            "You are a helpful academic writing assistant. "
            "Answer the user's questions clearly and concisely."
        )
    return _system_prompt_cache


def get_paper_context(paper_id: str | None) -> str:
    """Build full paper data JSON for the AI system prompt.

    Returns the complete paper JSON so the AI always has up-to-date
    context (title, abstract, sections with full content, references, etc.)
    and can edit it via [APPLY_PAPER] tags.
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

    # Serialize full paper JSON — AI sees everything
    try:
        paper_json = json.dumps(data, indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        paper_json = str(data)

    # Cap at ~30000 chars to avoid blowing up context window on very large papers
    if len(paper_json) > 30000:
        paper_json = paper_json[:30000] + "\n... [TRUNCATED — paper data exceeds 30K chars]"

    return paper_json


# ─── Conversation CRUD ─────────────────────────────────────────────────────


@simple_chat.route("/api/papers/<paper_id>/conversations", methods=["GET"])
@jwt_required()
def list_paper_conversations(paper_id):
    user_id = _current_user_id()
    if user_id is None:
        return {"error": "Unauthorized"}, 401
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return {"error": "Paper not found"}, 404
    convs = (
        Conversation.query.filter_by(user_id=user_id, paper_id=paper_id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )
    return [c.to_dict() for c in convs]


@simple_chat.route("/api/papers/<paper_id>/conversations", methods=["POST"])
@jwt_required()
def create_paper_conversation(paper_id):
    user_id = _current_user_id()
    if user_id is None:
        return {"error": "Unauthorized"}, 401
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return {"error": "Paper not found"}, 404
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "New Chat").strip() or "New Chat"
    conv = Conversation(
        id=_gen_id(),
        user_id=user_id,
        paper_id=paper_id,
        title=title,
    )
    db.session.add(conv)
    db.session.commit()
    return conv.to_dict()


@simple_chat.route("/api/chat/conversations/<conv_id>", methods=["GET"])
@jwt_required()
def get_conversation(conv_id: str):
    user_id = _current_user_id()
    if user_id is None:
        return {"error": "Unauthorized"}, 401
    conv = Conversation.query.filter_by(id=conv_id, user_id=user_id).first()
    if not conv:
        return {"error": "Conversation not found"}, 404
    msgs = (
        ChatMessage.query.filter_by(conversation_id=conv_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return {
        **conv.to_dict(),
        "messages": [m.to_dict() for m in msgs],
    }


@simple_chat.route("/api/chat/conversations/<conv_id>", methods=["PATCH"])
@jwt_required()
def rename_conversation(conv_id: str):
    user_id = _current_user_id()
    if user_id is None:
        return {"error": "Unauthorized"}, 401
    conv = Conversation.query.filter_by(id=conv_id, user_id=user_id).first()
    if not conv:
        return {"error": "Conversation not found"}, 404
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return {"error": "Title is required"}, 400
    conv.title = title
    db.session.commit()
    return {"ok": True}


@simple_chat.route("/api/chat/conversations/<conv_id>", methods=["DELETE"])
@jwt_required()
def delete_conversation(conv_id: str):
    user_id = _current_user_id()
    if user_id is None:
        return {"error": "Unauthorized"}, 401
    conv = Conversation.query.filter_by(id=conv_id, user_id=user_id).first()
    if not conv:
        return {"error": "Conversation not found"}, 404
    ChatMessage.query.filter_by(conversation_id=conv_id).delete()
    db.session.delete(conv)
    db.session.commit()
    return {"ok": True}


@simple_chat.route("/api/chat/conversations/<conv_id>/clear", methods=["POST"])
@jwt_required()
def clear_conversation(conv_id: str):
    """Delete all messages in a conversation but keep the conversation itself."""
    user_id = _current_user_id()
    if user_id is None:
        return {"error": "Unauthorized"}, 401
    conv = Conversation.query.filter_by(id=conv_id, user_id=user_id).first()
    if not conv:
        return {"error": "Conversation not found"}, 404
    deleted = ChatMessage.query.filter_by(conversation_id=conv_id).delete()
    conv.title = "New Chat"
    db.session.commit()
    log.info("Cleared %d messages from conv=%s", deleted, conv_id)
    return {"ok": True, "deleted": deleted}


@simple_chat.route("/api/chat/conversations/<conv_id>/messages", methods=["POST"])
@jwt_required()
def send_message(conv_id: str):
    user_id = _current_user_id()
    if user_id is None:
        return {"error": "Unauthorized"}, 401

    conv = Conversation.query.filter_by(id=conv_id, user_id=user_id).first()
    if not conv:
        return {"error": "Conversation not found"}, 404

    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content:
        return {"error": "Message content is required"}, 400
    if len(content) > 16000:
        return {"error": "Message is too long (max 16000 chars)"}, 400

    log.info("simple_chat.send conv=%s user=%s len=%d", conv_id, user_id, len(content))

    # Save user message to database
    try:
        user_msg = ChatMessage(conversation_id=conv_id, role="user", content=content)
        db.session.add(user_msg)

        if conv.title in (None, "", "New Chat"):
            conv.title = (content[:60] + ("\u2026" if len(content) > 60 else "")) or "New Chat"
        db.session.commit()
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
    # sebagai reference context. Tag @slr dihapus dari pesan sebelum ke AI.
    slr_tag_detected = False
    if "@slr" in content.lower():
        slr_tag_detected = True
        # Hapus @slr dari konten user (case-insensitive)
        content = re.sub(r"@slr\b", "", content, flags=re.IGNORECASE).strip()
        if conv.paper_id:
            try:
                pinned_text = get_pinned_literature(conv.paper_id, user_id, max_items=10)
                if pinned_text:
                    system_content += f"## SLR References (Pinned)\n{pinned_text}\n\n"
                    log.info("@slr tag: injected %d pinned literature items for paper=%s", pinned_text.count("\n[") + 1, conv.paper_id)
                else:
                    log.info("@slr tag: no pinned literature for paper=%s", conv.paper_id)
            except Exception as e:
                log.warning("@slr tag: failed to load pinned literature: %s", e)

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
            _REDIS.setex(_stream_key(conv_id), 1800, json.dumps(stream_state))  # 30 min TTL
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

            response_p1, model_used = route_chat_call(
                json={
                    "messages": messages_phase1,
                    "stream": True,
                    "max_tokens": 4096,
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

            # ── Check for search tags in phase 1 response ─────────────
            search_tags = []
            try:
                from tools.chat.search_tools import extract_search_tags
                search_tags = extract_search_tags(phase1_text)
            except Exception as e:
                log.warning("Failed to extract search tags: %s", e)

            # ── If no search tags → single-phase: stream phase 1 directly ─
            if not search_tags:
                # Stream phase 1 thinking
                if phase1_thinking:
                    thinking_content = phase1_thinking
                    yield _sse("thinking", {"content": phase1_thinking})
                    # Update Redis state
                    stream_state["thinking"] = thinking_content
                    try:
                        _REDIS.setex(_stream_key(conv_id), 1800, json.dumps(stream_state))
                    except Exception:
                        pass

                # Stream phase 1 text
                assistant_content = phase1_text
                yield _sse("text", {"content": phase1_text})
                # Update Redis state
                stream_state["content"] = assistant_content
                try:
                    _REDIS.setex(_stream_key(conv_id), 1800, json.dumps(stream_state))
                except Exception:
                    pass

            else:
                # ── PHASE 1.5: Execute searches with real-time progress ──
                log.info("Search tags found: %d — executing for conv=%s", len(search_tags), conv_id)

                # Show phase 1 thinking as reasoning (user sees AI's plan)
                if phase1_thinking:
                    thinking_content = phase1_thinking
                    yield _sse("thinking", {"content": phase1_thinking})

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

                response_p2, model_used = route_chat_call(
                    json={
                        "messages": messages_phase2,
                        "stream": True,
                        "max_tokens": 4096,
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
                        yield _sse("text", {"content": text})
                        # Update Redis state (batch updates, not every chunk)
                        stream_state["content"] = assistant_content
                        try:
                            _REDIS.setex(_stream_key(conv_id), 1800, json.dumps(stream_state))
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
                            # Update Redis state
                            stream_state["thinking"] = thinking_content
                            try:
                                _REDIS.setex(_stream_key(conv_id), 1800, json.dumps(stream_state))
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

            # Parse [APPLY_PAPER] tags using tools.py
            parsed = parse_completion(assistant_content)
            if parsed["has_operations"] and conv.paper_id:
                result = apply_operations(conv.paper_id, parsed["operations"])
                yield _sse("paper_applied", {
                    "operations": parsed["operations"],
                    "results": result["results"],
                    "errors": result["errors"],
                })
                assistant_content = parsed["cleaned_text"] if parsed["cleaned_text"] else assistant_content
                yield _sse("replace_text", {"content": assistant_content})

            # Streaming done — save assistant message to DB
            if assistant_content:
                assistant_msg = ChatMessage(
                    conversation_id=conv_id,
                    role="assistant",
                    content=assistant_content,
                )
                db.session.add(assistant_msg)
                db.session.commit()

                try:
                    fs_data = {
                        "content": assistant_content,
                        "message_id": assistant_msg.id,
                        "model": model_used,
                        "conv_id": conv_id,
                    }
                    if thinking_content:
                        fs_data["thinking"] = thinking_content
                    save_chat_recv_by_id(
                        username=username,
                        paper_id=conv.paper_id,
                        data=fs_data,
                        conv_id=conv_id,
                    )
                except Exception as e:
                    log.warning("Failed to save assistant message to filesystem: %s", e)

                yield _sse("done", {"message_id": assistant_msg.id})
                # Mark stream as done in Redis
                stream_state["status"] = "done"
                stream_state["message_id"] = assistant_msg.id
                try:
                    _REDIS.setex(_stream_key(conv_id), 60, json.dumps(stream_state))  # 1 min TTL for done state
                except Exception:
                    pass
            else:
                yield _sse("error", {"message": "AI returned an empty response."})
                # Mark stream as error in Redis
                stream_state["status"] = "error"
                stream_state["error"] = "Empty response"
                try:
                    _REDIS.setex(_stream_key(conv_id), 60, json.dumps(stream_state))
                except Exception:
                    pass

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
                _REDIS.setex(_stream_key(conv_id), 60, json.dumps(stream_state))
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
        raw = _REDIS.get(_stream_key(conv_id))
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
        raw = _REDIS.get(_stream_key(conv_id))
        if not raw:
            return jsonify({"status": "not_found", "message": "No active stream"})
        
        state = json.loads(raw)
        if state.get("status") != "streaming":
            return jsonify({"status": state.get("status"), "message": "Stream not active"})
        
        # Mark as cancelled
        state["status"] = "cancelled"
        state["cancelled_at"] = datetime.now(timezone.utc).isoformat()
        _REDIS.setex(_stream_key(conv_id), 60, json.dumps(state))
        
        return jsonify({"status": "cancelled", "message": "Stream cancelled successfully"})
    except Exception as e:
        log.warning("Failed to cancel stream: %s", e)
        return jsonify({"error": "Failed to cancel stream"}), 500
