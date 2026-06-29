"""Chat Drafts API — CRUD for named drafts exported from chat conversations.

Drafts let users capture interesting chat snippets (with file context, SLR refs,
etc.) and re-inject them later as context in:
  - Paperfull tab (as selectable items → custom_prompt)
  - Chat (via `@draft <name>` tag)
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging

from utils.database.models import ChatDraft, ChatMessage, Conversation, Paper, PaperFile, db, safe_commit
from utils.core.user_storage import get_username
import uuid
log = logging.getLogger(__name__)

drafts_bp = Blueprint("drafts", __name__, url_prefix="/api/papers")


def _err(message, code="BAD_REQUEST", status=400):
    return jsonify({"error": message, "code": code}), status


# ── CREATE draft from conversation ─────────────────────────────────────────────
@drafts_bp.route("/<paper_id>/drafts", methods=["POST"])
@jwt_required()
def create_draft(paper_id: str):
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError):
        return _err("Invalid user identity", "UNAUTHORIZED", 401)

    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    content = (body.get("content") or "").strip()
    conversation_id = body.get("conversation_id")
    tags = body.get("tags") or []
    selected_message_ids = body.get("selected_message_ids")  # optional

    if not name:
        return _err("Draft name is required", "NAME_REQUIRED", 400)
    if len(name) > 200:
        return _err("Draft name too long (max 200 chars)", "NAME_TOO_LONG", 400)
    if len(name) < 2:
        return _err("Draft name too short (min 2 chars)", "NAME_TOO_SHORT", 400)

    # Validate paper ownership
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return _err("Paper not found", "NOT_FOUND", 404)

    # Validate conversation ownership if provided
    conv = None
    if conversation_id:
        conv = Conversation.query.filter_by(id=conversation_id, user_id=user_id).first()
        if not conv:
            return _err("Conversation not found", "CONVERSATION_NOT_FOUND", 404)

    # If no content provided but conversation is specified, build from messages
    if not content and conv:
        try:
            if selected_message_ids:
                # Export specific messages (user selected)
                msgs = (
                    db.session.query(ChatMessage)
                    .filter(
                        ChatMessage.id.in_(selected_message_ids),
                        ChatMessage.conversation_id == conversation_id,
                    )
                    .order_by(ChatMessage.created_at.asc())
                    .all()
                )
            else:
                # Export whole conversation
                msgs = (
                    db.session.query(ChatMessage)
                    .filter_by(conversation_id=conversation_id)
                    .order_by(ChatMessage.created_at.asc())
                    .limit(200)
                    .all()
                )

            if msgs:
                lines = []
                for m in msgs:
                    role = m.role.upper() if m.role else "USER"
                    text = (m.content or "").strip()
                    if not text:
                        continue
                    lines.append(f"**{role}**:\n{text}")
                content = "\n\n".join(lines)
        except Exception as e:
            log.warning("[create_draft] failed to build content from conversation: %s", e)

    if not content:
        return _err(
            "Draft content is empty. Provide content or select a conversation with messages.",
            "CONTENT_EMPTY",
            400,
        )

    # Check duplicate name (per paper + user) — upsert if exists
    existing = (
        ChatDraft.query.filter_by(paper_id=paper_id, user_id=user_id, name=name).first()
    )
    if existing:
        existing.content = content
        existing.conversation_id = conversation_id or existing.conversation_id
        existing.tags = tags if isinstance(tags, list) else existing.tags or []
        draft = existing
        log.info("[create_draft] upsert paper=%s user=%s name=%s conv=%s len=%d",
                 paper_id, user_id, name, conversation_id, len(content))
    else:
        draft = ChatDraft(
            paper_id=paper_id,
            user_id=user_id,
            conversation_id=conversation_id,
            name=name,
            content=content,
            tags=tags if isinstance(tags, list) else [],
        )
        db.session.add(draft)

    try:
        safe_commit()
    except Exception as e:
        log.exception("[create_draft] commit failed: %s", e)
        return _err(f"Failed to save draft: {e}", "DB_ERROR", 500)

    # Also create a PaperFile so the draft appears in the Files tab
    log.info("[create_draft] Creating PaperFile for draft %s", name)
    file_entry = None
    try:
        original_name = f"draft-{name}.md"
        stored_name = f"{uuid.uuid4().hex}.md"
        file_entry = PaperFile(
            paper_id=paper_id,
            user_id=user_id,
            filename=stored_name,
            original_name=original_name,
            ext=".md",
            size_bytes=len(content.encode("utf-8")),
            file_path="",  # no raw binary persisted
            extracted_text=content,
        )
        db.session.add(file_entry)
        safe_commit()
        log.info("[create_draft] PaperFile id=%s created for draft %s", file_entry.id, name)
    except Exception as e:
        log.warning("[create_draft] failed to create PaperFile for draft %s: %s", name, e)
        file_entry = None

    log.info(
        "[create_draft] paper=%s user=%s name=%s conv=%s len=%d",
        paper_id,
        user_id,
        name,
        conversation_id,
        len(content),
    )
    resp = {"ok": True, "draft": draft.to_dict(include_content=True)}
    if file_entry:
        resp["paper_file"] = file_entry.to_dict(include_text=False)
    return jsonify(resp), 201


# ── LIST drafts for a paper ─────────────────────────────────────────────────────
@drafts_bp.route("/<paper_id>/drafts", methods=["GET"])
@jwt_required()
def list_drafts(paper_id: str):
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError):
        return _err("Invalid user identity", "UNAUTHORIZED", 401)

    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return _err("Paper not found", "NOT_FOUND", 404)

    # Filters
    name_q = (request.args.get("name") or "").strip()
    tag_q = (request.args.get("tag") or "").strip()
    try:
        limit = int(request.args.get("limit", 50))
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(limit, 200))

    q = ChatDraft.query.filter_by(paper_id=paper_id, user_id=user_id)
    if name_q:
        q = q.filter(ChatDraft.name.ilike(f"%{name_q}%"))

    rows = q.order_by(ChatDraft.updated_at.desc()).limit(limit).all()

    # Apply tag filter in python (tags is JSON list)
    if tag_q:
        rows = [r for r in rows if tag_q.lower() in [str(t).lower() for t in (r.tags or [])]]

    return jsonify({
        "drafts": [r.to_dict(include_content=False) for r in rows],
        "total": len(rows),
    })


# ── GET single draft (with content) ─────────────────────────────────────────────
@drafts_bp.route("/<paper_id>/drafts/<int:draft_id>", methods=["GET"])
@jwt_required()
def get_draft(paper_id: str, draft_id: int):
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError):
        return _err("Invalid user identity", "UNAUTHORIZED", 401)

    draft = ChatDraft.query.filter_by(id=draft_id, paper_id=paper_id, user_id=user_id).first()
    if not draft:
        return _err("Draft not found", "NOT_FOUND", 404)

    return jsonify({"draft": draft.to_dict(include_content=True)})


# ── DELETE draft ───────────────────────────────────────────────────────────────
@drafts_bp.route("/<paper_id>/drafts/<int:draft_id>", methods=["DELETE"])
@jwt_required()
def delete_draft(paper_id: str, draft_id: int):
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError):
        return _err("Invalid user identity", "UNAUTHORIZED", 401)

    draft = ChatDraft.query.filter_by(id=draft_id, paper_id=paper_id, user_id=user_id).first()
    if not draft:
        return _err("Draft not found", "NOT_FOUND", 404)

    db.session.delete(draft)
    try:
        safe_commit()
    except Exception as e:
        return _err(f"Failed to delete draft: {e}", "DB_ERROR", 500)

    log.info("[delete_draft] paper=%s user=%s draft=%s (%s)", paper_id, user_id, draft_id, draft.name)
    return jsonify({"ok": True})


# ── UPDATE draft (rename or content) ────────────────────────────────────────────
@drafts_bp.route("/<paper_id>/drafts/<int:draft_id>", methods=["PATCH"])
@jwt_required()
def update_draft(paper_id: str, draft_id: int):
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError):
        return _err("Invalid user identity", "UNAUTHORIZED", 401)

    draft = ChatDraft.query.filter_by(id=draft_id, paper_id=paper_id, user_id=user_id).first()
    if not draft:
        return _err("Draft not found", "NOT_FOUND", 404)

    body = request.get_json(silent=True) or {}
    new_name = (body.get("name") or "").strip()
    new_content = body.get("content")
    new_tags = body.get("tags")

    if new_name:
        if len(new_name) > 200:
            return _err("Name too long (max 200 chars)", "NAME_TOO_LONG", 400)
        if new_name != draft.name:
            existing = ChatDraft.query.filter_by(
                paper_id=paper_id, user_id=user_id, name=new_name
            ).first()
            if existing:
                return _err(
                    f"Draft named '{new_name}' already exists",
                    "DUPLICATE_NAME",
                    409,
                )
            draft.name = new_name

    if new_content is not None:
        if isinstance(new_content, str):
            draft.content = new_content.strip()

    if new_tags is not None and isinstance(new_tags, list):
        draft.tags = new_tags

    try:
        safe_commit()
    except Exception as e:
        return _err(f"Failed to update draft: {e}", "DB_ERROR", 500)

    return jsonify({"ok": True, "draft": draft.to_dict(include_content=False)})


# ── Helper: resolve draft by name for chat injection ───────────────────────────
def get_drafts_by_names(paper_id: str, user_id: int, names: list[str], max_items: int = 5) -> str:
    """Fetch drafts by name, return formatted block for chat injection.

    Called by chat.py when user writes `@draft <name>` or `@draft name1,name2`.
    Returns empty string if nothing matches or query fails.
    """
    if not paper_id or not user_id or not names:
        return ""
    names_clean = [n.strip() for n in names if n and n.strip()]
    if not names_clean:
        return ""

    try:
        drafts = (
            ChatDraft.query.filter(
                ChatDraft.paper_id == paper_id,
                ChatDraft.user_id == user_id,
                ChatDraft.name.in_(names_clean),
            )
            .limit(max_items)
            .all()
        )
        if not drafts:
            return ""

        parts = []
        for d in drafts:
            body = (d.content or "").strip()
            # Cap to 2KB per draft to keep prompt budget sane
            if len(body) > 2000:
                body = body[:2000] + "\n...[truncated]"
            parts.append(f"### Draft: {d.name}\n{body}")
        return "\n\n".join(parts).strip()
    except Exception as e:
        log.warning("[get_drafts_by_names] failed for paper=%s names=%s: %s", paper_id, names, e)
        return ""
