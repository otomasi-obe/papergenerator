"""
Simple streaming chat — no tools, no workflow, no mode system.
User message → get memory → call AI → stream SSE → save message.
"""

import json
import logging
import os
import uuid

from flask import Blueprint, Response, request, stream_with_context
from flask_jwt_extended import get_jwt_identity, jwt_required

from sqlalchemy import desc

from database.models import ChatMessage, Conversation, Paper, ProjectMemory, User, db
from utils.ai_tools.model_router import route_chat_call
from utils.core.user_storage import get_username, save_chat_send_by_id, save_chat_recv_by_id

log = logging.getLogger(__name__)

simple_chat = Blueprint("simple_chat", __name__)


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


def load_system_prompt() -> str:
    global _system_prompt_cache
    if _system_prompt_cache is not None:
        return _system_prompt_cache
    path = os.path.join(os.path.dirname(__file__), "chatPrompt.txt")
    try:
        with open(path, "r", encoding="utf-8") as f:
            _system_prompt_cache = f.read()
    except FileNotFoundError:
        log.warning("chatPrompt.txt not found at %s, using fallback prompt", path)
        _system_prompt_cache = (
            "You are a helpful academic writing assistant. "
            "Answer the user's questions clearly and concisely."
        )
    return _system_prompt_cache


def get_memory_context(paper_id: str | None, conv_id: str | None) -> str:
    """Build a system-prompt context snippet from ProjectMemory entries.

    Returns a formatted string of memory entries scoped to the paper
    (global + conversation-scoped), or an empty string if none exist.
    """
    if not paper_id:
        return ""

    paper = Paper.query.get(paper_id)
    paper_header = f"Paper: {paper.title if paper else 'Untitled'}\nPaper ID: {paper_id}\n"

    # Include paper JSON data (truncated summary only, not full JSON)
    paper_data_str = ""
    if paper and paper.data:
        try:
            sections = paper.data.get("sections", []) if isinstance(paper.data, dict) else []
            metadata = paper.data.get("metadata", {}) if isinstance(paper.data, dict) else {}
            title = paper.data.get("title", "") or paper.title or ""
            abstract = paper.data.get("abstract", "") or metadata.get("abstract", "")

            summary = {"title": title}
            if abstract:
                summary["abstract"] = abstract[:1000]
            if metadata:
                summary["metadata"] = {
                    k: v for k, v in metadata.items()
                    if isinstance(v, (str, int, float, bool)) and not isinstance(v, bool)
                }

            section_headers = []
            for s in sections[:20]:
                if isinstance(s, dict):
                    h = s.get("title") or s.get("heading") or s.get("section_title") or ""
                    if h:
                        section_headers.append(h)

            if section_headers:
                summary["sections"] = section_headers

            paper_data_str = f"\nPaper Data:\n{json.dumps(summary, ensure_ascii=False, indent=2)}\n"
        except (TypeError, ValueError) as e:
            log.warning("Failed to serialize paper.data: %s", e)
            paper_data_str = ""

    entries = (
        ProjectMemory.query.filter(
            ProjectMemory.paper_id == paper_id,
            (ProjectMemory.conversation_id.is_(None))
            | (ProjectMemory.conversation_id == conv_id),
        )
        .order_by(ProjectMemory.updated_at.desc())
        .all()
    )

    if not entries:
        return paper_header + "No memory entries yet." + paper_data_str

    lines = [paper_header, "Known facts about this project:"]
    for e in entries:
        lines.append(f"- [{e.kind}] {e.key}: {e.value}")

    return "\n".join(lines) + paper_data_str


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
        title=title[:120],
    )
    db.session.add(conv)
    try:
        db.session.commit()
        db.session.refresh(conv)
        return conv.to_dict(), 201
    except Exception as e:
        db.session.rollback()
        log.exception("Failed to create conversation for paper=%s: %s", paper_id, e)
        return {"error": "Failed to create conversation"}, 500


@simple_chat.route("/api/chat/conversations/<conv_id>", methods=["GET"])
@jwt_required()
def get_conversation(conv_id):
    user_id = _current_user_id()
    if user_id is None:
        return {"error": "Unauthorized"}, 401
    conv = Conversation.query.filter_by(id=conv_id, user_id=user_id).first()
    if not conv:
        return {"error": "Conversation not found"}, 404
    return conv.to_dict(include_messages=True)


@simple_chat.route("/api/chat/conversations/<conv_id>", methods=["PATCH"])
@jwt_required()
def rename_conversation(conv_id):
    user_id = _current_user_id()
    if user_id is None:
        return {"error": "Unauthorized"}, 401
    conv = Conversation.query.filter_by(id=conv_id, user_id=user_id).first()
    if not conv:
        return {"error": "Conversation not found"}, 404
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return {"error": "title is required"}, 400
    conv.title = title[:120]
    db.session.commit()
    return conv.to_dict()


@simple_chat.route("/api/chat/conversations/<conv_id>", methods=["DELETE"])
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


@simple_chat.route("/api/papers/<paper_id>/memory", methods=["GET"])
@jwt_required()
def list_memory(paper_id):
    user_id = _current_user_id()
    if user_id is None:
        return {"error": "Unauthorized"}, 401
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return {"error": "Paper not found"}, 404
    entries = (
        ProjectMemory.query.filter_by(paper_id=paper_id)
        .order_by(ProjectMemory.updated_at.desc())
        .all()
    )
    return [e.to_dict() for e in entries]


@simple_chat.route("/api/papers/<paper_id>/memory/<int:mem_id>", methods=["DELETE"])
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
    user_msg = ChatMessage(conversation_id=conv_id, role="user", content=content)
    db.session.add(user_msg)

    if conv.title in (None, "", "New Chat"):
        conv.title = (content[:60] + ("\u2026" if len(content) > 60 else "")) or "New Chat"
    db.session.commit()

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

    # Build system prompt with memory context
    memory_block = get_memory_context(conv.paper_id, conv.id)
    system_content = load_system_prompt().rstrip("\n") + "\n\n"
    if conv.paper_id and memory_block:
        system_content += f"## Project Context\n{memory_block}\n\n"
    system_content += (
        "## Instructions\n"
        "- Be helpful, accurate, and concise.\n"
        "- Use Indonesian or English following the user's language.\n"
        "- Do NOT use any tools or functions.\n"
    )

    def generate():
        # Temporarily disabled: if request.is_disconnected(): return
        
        assistant_content = ""
        log.info("Chat generate started for conv_id=%s", conv_id)

        try:
            # Build message list: system + history + current user message
            messages = [{"role": "system", "content": system_content}]

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
                messages.append({"role": role, "content": msg.content})

            # Use route_chat_call which handles model fallback + retry
            response, model_used = route_chat_call(
                json={
                    "messages": messages,
                    "stream": True,
                    "max_tokens": 4096,
                },
                stream=True,
                timeout=900,
            )

            for line in response.iter_lines():
                # Temporarily disabled: if request.is_disconnected(): return

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

                if "thinking" in delta and delta["thinking"]:
                    thinking = delta.get("thinking", "")
                    if isinstance(thinking, dict):
                        thinking = thinking.get("content", "")
                    if thinking:
                        yield _sse("thinking", {"content": thinking})


            # Streaming done — save assistant message to DB
            if assistant_content:
                assistant_msg = ChatMessage(
                    conversation_id=conv_id,
                    role="assistant",
                    content=assistant_content,
                )
                db.session.add(assistant_msg)
                db.session.commit()

                # Save to filesystem after DB commit (ID is now available)
                try:
                    save_chat_recv_by_id(
                        username=username,
                        paper_id=conv.paper_id,
                        data={
                            "content": assistant_content,
                            "message_id": assistant_msg.id,
                            "model": model_used,
                            "conv_id": conv_id,
                        },
                        conv_id=conv_id,
                    )
                except Exception as e:
                    log.warning("Failed to save assistant message to filesystem: %s", e)

                yield _sse("done", {"message_id": assistant_msg.id})
            else:
                yield _sse("error", {"message": "AI returned an empty response."})

        except Exception as e:
            db.session.rollback()
            log.exception("simple_chat stream failed: conv=%s", conv_id)
            yield _sse("error", {"message": "AI call failed. Please try again."})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
