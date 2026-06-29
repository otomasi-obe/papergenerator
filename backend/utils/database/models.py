"""
Database Models for PaperFull
=====================================
SQLAlchemy models for users, papers, images, and API usage logs.
"""

from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import JSON
from sqlalchemy.orm import validates
from sqlalchemy.dialects.postgresql import JSONB
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


def safe_commit(*, reraise: bool = True) -> bool:
    """Commit the current session; on failure roll back so the session is not
    left in a broken state (critical in long-lived RQ workers where the same
    scoped session is reused across jobs — an uncommitted failure otherwise
    poisons every subsequent query with PendingRollbackError).

    Returns True on success. Re-raises by default; pass reraise=False to
    swallow the error after rollback (best-effort writes).
    """
    try:
        db.session.commit()
        return True
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        if reraise:
            raise
        return False



def _utcnow():
    return datetime.now(timezone.utc)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    google_id = db.Column(db.String(100), unique=True, nullable=True)
    oauth_provider = db.Column(db.String(20), nullable=True)  # 'google', 'github', etc.
    email = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    password_hash = db.Column(db.String(255), nullable=True)
    avatar_url = db.Column(db.String(500))
    role = db.Column(db.String(20), default="user")  # 'user' or 'admin'
    created_at = db.Column(db.DateTime, default=_utcnow)
    last_login = db.Column(db.DateTime, default=_utcnow)
    # Token quota (admin-managed via /api/admin/users/<id>/quota)
    token_quota_monthly = db.Column(db.Integer, default=1000000, nullable=False)
    token_used_month = db.Column(db.Integer, default=0, nullable=False)
    usage_month_key = db.Column(db.String(7), default="")  # 'YYYY-MM'
    # Settings
    nickname = db.Column(db.String(100), nullable=True, default="")
    institution = db.Column(db.String(255), nullable=True, default="")
    preferred_language = db.Column(db.String(10), nullable=True, default="id")  # 'id' or 'en'

    # BUG-11: Validate enum-like fields at the ORM level
    @validates("role")
    def _validate_role(self, key, value):
        allowed = ("user", "admin")
        if value is not None and value not in allowed:
            raise ValueError(f"User.role must be one of {allowed}, got {value!r}")
        return value

    @validates("preferred_language")
    def _validate_preferred_language(self, key, value):
        allowed = ("id", "en")
        if value is not None and value not in allowed:
            raise ValueError(f"User.preferred_language must be one of {allowed}, got {value!r}")
        return value

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    papers = db.relationship("Paper", backref="user", lazy=True, cascade="all, delete-orphan")
    usage_logs = db.relationship("ApiUsageLog", backref="user", lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "avatar_url": self.avatar_url,
            "role": self.role,
            "oauth_provider": self.oauth_provider or ("google" if self.google_id else None),
            "created_at": self.created_at.isoformat(),
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "token_quota_monthly": self.token_quota_monthly,
            "token_used_month": self.token_used_month,
            "usage_month_key": self.usage_month_key,
            "nickname": self.nickname or "",
            "institution": self.institution or "",
            "preferred_language": self.preferred_language or "id",
        }


class Paper(db.Model):
    __tablename__ = "papers"

    id = db.Column(db.String(20), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.Text, default="Untitled")
    data = db.Column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)
    active_operation = db.Column(db.String(50), nullable=True)
    active_operation_job_id = db.Column(db.String(50), nullable=True)
    active_operation_started_at = db.Column(db.DateTime, nullable=True)
    # Optimistic-locking column. Present for explicit concurrency checks in
    # write paths that opt in (compare-and-set). NOT wired to SQLAlchemy's
    # automatic version_id_col on purpose: the autosave + AI-generation write
    # paths run concurrently and only catch OperationalError/DBAPIError, so an
    # automatic StaleDataError would surface as uncaught 500s / worker crashes.
    version = db.Column(db.Integer, nullable=False, default=1)

    images = db.relationship("PaperImage", backref="paper", lazy=True, cascade="all, delete-orphan")
    files = db.relationship("PaperFile", backref="paper", lazy=True, cascade="all, delete-orphan")
    conversations = db.relationship(
        "Conversation", backref="paper", lazy=True, cascade="all, delete-orphan"
    )
    memory_entries = db.relationship(
        "ProjectMemory", backref="paper", lazy=True, cascade="all, delete-orphan"
    )

    def to_dict(self, include_data=False, image_count=None):
        # BUG-22: image_count query causes N+1 when listing many papers.
        # Pass pre-loaded image_count to skip the per-row query.
        if image_count is None:
            image_count = db.session.query(db.func.count(PaperImage.id)).filter_by(paper_id=self.id).scalar() or 0
        result = {
            "id": self.id,
            "title": self.title,
            "user_id": self.user_id,
            "image_count": image_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
        if include_data:
            result["data"] = self.data
        return result


class PaperImage(db.Model):
    __tablename__ = "paper_images"

    id = db.Column(db.Integer, primary_key=True)
    paper_id = db.Column(db.String(20), db.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)  # stored filename (uuid-based)
    original_name = db.Column(db.String(255), nullable=False)  # original upload name
    file_path = db.Column(db.String(500), nullable=False)  # relative path in data/uploads/
    created_at = db.Column(db.DateTime, default=_utcnow)

    def to_dict(self):
        from urllib.parse import quote
        return {
            "id": self.id,
            "paper_id": self.paper_id,
            "filename": self.filename,
            "original_name": self.original_name,
            "url": f"/api/images/{self.paper_id}/{quote(self.filename, safe='')}",
            "created_at": self.created_at.isoformat(),
        }


class PaperFile(db.Model):
    """Generic file (pdf/docx/doc/txt/md) attached to a paper for the Files tab."""

    __tablename__ = "paper_files"

    id = db.Column(db.Integer, primary_key=True)
    paper_id = db.Column(db.String(20), db.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)  # stored filename (uuid-based)
    original_name = db.Column(db.String(255), nullable=False)  # original upload name
    ext = db.Column(db.String(10), nullable=False)  # .pdf .docx etc
    size_bytes = db.Column(db.Integer, default=0)
    file_path = db.Column(db.String(500), nullable=False)  # relative path in data/uploads/
    extracted_text = db.Column(db.Text, default="")  # cached text for preview
    # PDF metadata — extracted during upload before file is deleted
    meta_title = db.Column(db.Text, default="")
    meta_authors = db.Column(JSON().with_variant(JSONB, "postgresql"), default=list)  # list[str]
    meta_doi = db.Column(db.String(500), default="")
    meta_year = db.Column(db.Integer, nullable=True)
    meta_abstract = db.Column(db.Text, default="")
    meta_venue = db.Column(db.String(500), default="")
    meta_publisher = db.Column(db.String(500), default="")
    created_at = db.Column(db.DateTime, default=_utcnow)

    def to_dict(self, include_text=False):
        d = {
            "id": self.id,
            "paper_id": self.paper_id,
            "filename": self.filename,
            "original_name": self.original_name,
            "ext": self.ext,
            "size_bytes": self.size_bytes,
            "url": f"/api/papers/{self.paper_id}/files/{self.id}/raw",
            "preview_url": f"/api/papers/{self.paper_id}/files/{self.id}/preview",
            "created_at": self.created_at.isoformat(),
        }
        if include_text:
            d["text"] = self.extracted_text or ""
        return d


class ApiUsageLog(db.Model):
    __tablename__ = "api_usage_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    endpoint = db.Column(db.String(100), nullable=False)
    prompt_tokens = db.Column(db.Integer, default=0)
    completion_tokens = db.Column(db.Integer, default=0)
    total_tokens = db.Column(db.Integer, default=0)
    model = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=_utcnow)


class Conversation(db.Model):
    """Chat thread inside a paper project. One paper can have many chats."""

    __tablename__ = "conversations"

    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    paper_id = db.Column(db.String(20), db.ForeignKey("papers.id", ondelete="CASCADE"), nullable=True)
    title = db.Column(db.Text, default="New Chat")
    mode = db.Column(db.String(30), nullable=True, default=None)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    messages = db.relationship(
        "ChatMessage",
        backref="conversation",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )

    def to_dict(self, include_messages=False, message_count=None):
        # BUG: message_count query runs per-row -> N+1 when listing conversations.
        # Pass a pre-computed count to skip the per-row query; default keeps
        # to_dict() working standalone (backward compatible).
        if message_count is None:
            message_count = (
                db.session.query(db.func.count(ChatMessage.id))
                .filter_by(conversation_id=self.id)
                .scalar()
                or 0
            )
        result = {
            "id": self.id,
            "user_id": self.user_id,
            "paper_id": self.paper_id,
            "title": self.title,
            "mode": self.mode,
            "message_count": message_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
        if include_messages:
            result["messages"] = [m.to_dict() for m in self.messages]
        return result


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.String(36), db.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, default="")
    thinking = db.Column(db.Text, nullable=True)
    tool_calls = db.Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "role": self.role,
            "content": self.content,
            "thinking": self.thinking,
            "tool_calls": self.tool_calls,
            "created_at": self.created_at.isoformat(),
        }


class ProjectMemory(db.Model):
    """Per-paper memory entries shared by all chats inside that paper.

    The AI saves facts here (judul tentatif, metodologi, gaya bahasa, dll) via
    the SaveMemory tool, and reads them back at the start of every conversation.

    Memory entries are scoped:
    - `conversation_id IS NULL` -> paper-global memory (visible to every chat
      in the paper).
    - `conversation_id = '<id>'` -> chat-scoped memory (only that chat sees it,
      and it is deleted when the chat is deleted).

    Two partial unique indexes enforce uniqueness of `key` per scope:
    - `uq_pm_paper_key_global`: one row per (paper_id, key) when global.
    - `uq_pm_paper_conv_key`: one row per (paper_id, conversation_id, key) when
      chat-scoped.
    """

    __tablename__ = "project_memory"

    id = db.Column(db.Integer, primary_key=True)
    paper_id = db.Column(db.String(20), db.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    conversation_id = db.Column(
        db.String(36),
        db.ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    key = db.Column(db.String(120), nullable=False)
    value = db.Column(db.Text, nullable=False)
    kind = db.Column(db.String(40), default="fact")
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        db.Index(
            "uq_pm_paper_key_global",
            "paper_id",
            "key",
            unique=True,
            postgresql_where=db.text("conversation_id IS NULL"),
            sqlite_where=db.text("conversation_id IS NULL"),
        ),
        db.Index(
            "uq_pm_paper_conv_key",
            "paper_id",
            "conversation_id",
            "key",
            unique=True,
            postgresql_where=db.text("conversation_id IS NOT NULL"),
            sqlite_where=db.text("conversation_id IS NOT NULL"),
        ),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "paper_id": self.paper_id,
            "conversation_id": self.conversation_id,
            "key": self.key,
            "value": self.value,
            "kind": self.kind,
            "updated_at": self.updated_at.isoformat(),
        }


class AiJob(db.Model):
    __tablename__ = "ai_jobs"

    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    paper_id = db.Column(db.String(20), db.ForeignKey("papers.id", ondelete="SET NULL"), nullable=True, index=True)
    kind = db.Column(db.String(30), nullable=False, default="generate_paper")
    status = db.Column(
        db.String(20), nullable=False, default="queued"
    )  # queued|running|paused|done|error|cancelled

    # BUG-11: Validate status at the ORM level
    @validates("status")
    def _validate_status(self, key, value):
        allowed = ("queued", "running", "paused", "done", "error", "cancelled")
        if value is not None and value not in allowed:
            raise ValueError(f"AiJob.status must be one of {allowed}, got {value!r}")
        return value

    progress = db.Column(db.Integer, default=0)  # 0..100
    stage = db.Column(db.String(60), default="")  # 'outline' | 'sections' | 'references' | ...
    prompt = db.Column(db.Text)
    result = db.Column(JSON().with_variant(JSONB, "postgresql"), nullable=True, default=dict)
    error = db.Column(db.Text)
    timeout = db.Column(db.Boolean, default=False)
    started_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        db.Index("ix_ai_jobs_user_paper_kind", "user_id", "paper_id", "kind"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "paper_id": self.paper_id,
            "kind": self.kind,
            "status": self.status,
            "progress": self.progress,
            "stage": self.stage,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class LiteratureItem(db.Model):
    """One row in a paper's Literature tab.

    Bisa berasal dari hasil SLR (`source_kind='slr'`), upload PDF/DOCX
    (`source_kind='file'`), atau input manual user (`source_kind='manual'`).
    Editable via PATCH endpoint dan dipakai sebagai data sumber utk
    GenerateFullPaper.
    """

    __tablename__ = "literature_items"

    id = db.Column(db.Integer, primary_key=True)
    paper_id = db.Column(db.String(20), db.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source_kind = db.Column(db.String(20), default="slr")  # slr | file | manual
    source = db.Column(db.String(40), default="")  # arxiv|ieee|sinta|...
    title = db.Column(db.Text, default="")
    title_norm = db.Column(db.Text, nullable=True, default="")
    authors = db.Column(JSON().with_variant(JSONB, "postgresql"), nullable=True, default=list)  # list[str]
    year = db.Column(db.Integer, nullable=True)
    venue = db.Column(db.Text, default="")
    publisher = db.Column(db.Text, default="")
    doi = db.Column(db.String(255), nullable=True, index=True)
    url = db.Column(db.Text, default="")
    pdf_url = db.Column(db.Text, nullable=True)
    abstract = db.Column(db.Text, default="")
    summary = db.Column(db.Text, default="")
    citations = db.Column(db.Integer, nullable=True)
    score_total = db.Column(db.Float, nullable=True)
    score_breakdown = db.Column(JSON().with_variant(JSONB, "postgresql"), nullable=True, default=dict)
    must_read = db.Column(db.Boolean, default=False)
    is_relevant = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text, default="")  # user-editable notes
    gap_riset = db.Column(db.Text, default="")  # AI-generated research gap suggestion
    review = db.Column(db.Text, default="")  # AI-generated review (viola-chat)
    pinned = db.Column(db.Boolean, default=False)  # user-pinned to top
    is_checked = db.Column(db.Boolean, default=False, nullable=False, server_default=db.text("false"))
    file_id = db.Column(db.Integer, db.ForeignKey("paper_files.id", ondelete="SET NULL"), nullable=True)
    slr_job_id = db.Column(
        db.String(20), db.ForeignKey("slr_jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        db.Index(
            "uq_literature_paper_doi",
            "paper_id",
            "doi",
            unique=True,
            postgresql_where=db.text("doi IS NOT NULL"),
            sqlite_where=db.text("doi IS NOT NULL"),
        ),
        db.Index(
            "uq_literature_title_norm",
            "paper_id",
            "title_norm",
            unique=True,
            postgresql_where=db.text("title_norm IS NOT NULL AND title_norm != ''"),
            sqlite_where=db.text("title_norm IS NOT NULL AND title_norm != ''"),
        ),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "paper_id": self.paper_id,
            "source_kind": self.source_kind,
            "source": self.source,
            "title": self.title,
            "authors": self.authors or [],
            "year": self.year,
            "venue": self.venue,
            "publisher": self.publisher,
            "doi": self.doi,
            "url": self.url,
            "pdf_url": self.pdf_url,
            "abstract": self.abstract,
            "summary": self.summary,
            "citations": self.citations,
            "score_total": self.score_total,
            "score_breakdown": self.score_breakdown or {},
            "must_read": bool(self.must_read),
            "is_relevant": bool(self.is_relevant),
            "notes": self.notes or "",
            "gap_riset": self.gap_riset or "",
            "review": self.review or "",
            "pinned": bool(self.pinned),
            "is_checked": bool(self.is_checked),
            "file_id": self.file_id,
            "slr_job_id": self.slr_job_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ChatDraft(db.Model):
    """Named draft exported from a chat conversation.

    Drafts are snippets of discussion (or curated content) that the user
    wants to re-use as context when generating a full paper or when
    continuing a chat. They appear in:
      - Paperfull tab: as selectable items (selected_drafts)
      - Chat: via `@draft <name>` tag injection.
    """

    __tablename__ = "chat_drafts"

    id = db.Column(db.Integer, primary_key=True)
    paper_id = db.Column(db.String(20), db.ForeignKey("papers.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = db.Column(
        db.String(36), db.ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, default="")
    tags = db.Column(JSON().with_variant(JSONB, "postgresql"), nullable=True, default=list)  # optional tags for search
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    def to_dict(self, include_content: bool = False):
        d = {
            "id": self.id,
            "paper_id": self.paper_id,
            "user_id": self.user_id,
            "conversation_id": self.conversation_id,
            "name": self.name,
            "tags": self.tags or [],
            "content_length": len(self.content or ""),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_content:
            d["content"] = self.content or ""
        return d


class SlrJob(db.Model):
    """Background SLR search job. Diproses oleh slr_worker pool (≤10 worker)."""

    __tablename__ = "slr_jobs"

    id = db.Column(db.String(20), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    paper_id = db.Column(db.String(20), db.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = db.Column(db.String(36), db.ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True)
    query = db.Column(db.Text, nullable=False)
    sources = db.Column(JSON().with_variant(JSONB, "postgresql"), nullable=True, default=list)
    top_k = db.Column(db.Integer, default=50)
    per_source = db.Column(db.Integer, default=60)
    year_from = db.Column(db.Integer, nullable=True)
    ai_summarize = db.Column(db.Boolean, default=True)
    ai_model = db.Column(db.String(40), default="V-OPUS")

    status = db.Column(db.String(20), default="queued", index=True)
    # queued|running|done|error|cancelled
    stage = db.Column(db.String(40), default="")
    progress = db.Column(db.Integer, default=0)  # 0..100
    progress_message = db.Column(db.Text, default="")
    result = db.Column(JSON().with_variant(JSONB, "postgresql"), nullable=True, default=dict)
    """Full pipeline output. Callers MUST keep this small (top_k items + stats only);
    the worker is responsible for trimming large payloads before persisting."""
    error = db.Column(db.Text, default="")

    queued_at = db.Column(db.DateTime, default=_utcnow)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (db.Index("ix_slr_jobs_status_queued_at", "status", "queued_at"),)

    def to_dict(self, include_result=False):
        stats = (self.result or {}).get("stats") if isinstance(self.result, dict) else {}
        d = {
            "id": self.id,
            "paper_id": self.paper_id,
            "conversation_id": self.conversation_id,
            "query": self.query,
            "sources": self.sources or [],
            "top_k": self.top_k,
            "status": self.status,
            "stage": self.stage,
            "progress": int(self.progress or 0),
            "progress_message": self.progress_message or "",
            "error": self.error or "",
            "queued_at": self.queued_at.isoformat() if self.queued_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "stats": stats or {},
        }
        if include_result:
            d["result"] = self.result or {}
        return d


class ImageGenJob(db.Model):
    """Background job to generate an image via the Gemini pool.

    Workers (4, one per Gemini account) pick up `queued` jobs FIFO. Each worker
    drives one Gemini account exclusively, so up to 4 generations can run in
    parallel — one per account, never two on the same account. Within a single
    worker, generations are strictly sequential (the underlying Playwright
    profile cannot be shared concurrently).

    The job survives across paper switches and full page reloads: the frontend
    polls /api/image-jobs by user, attaches callbacks back to the matching
    content item, and writes `image_id` into the corresponding section content
    block when the worker finishes.
    """

    __tablename__ = "image_gen_jobs"

    id = db.Column(db.String(32), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    paper_id = db.Column(db.String(20), db.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True)
    prompt = db.Column(db.Text, nullable=False)
    status = db.Column(
        db.String(20), nullable=False, default="queued"
    )  # queued|running|done|error|cancelled
    worker = db.Column(
        db.String(40), nullable=True
    )  # which account picked it up (account1..account4)
    image_id = db.Column(db.Integer, db.ForeignKey("paper_images.id", ondelete="SET NULL"), nullable=True)
    error = db.Column(db.Text, nullable=True)  # error message if status=error
    retry_count = db.Column(db.Integer, default=0, nullable=False)  # job-level retry attempts
    target_path = db.Column(db.String(500), nullable=True)  # intended filename from paper JSON (e.g., "fig1_architecture.jpg")
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)
    started_at = db.Column(db.DateTime, nullable=True)  # when worker claimed the job
    finished_at = db.Column(db.DateTime, nullable=True)  # when job reached terminal state

    image = db.relationship("PaperImage", foreign_keys=[image_id])

    __table_args__ = (
        db.Index("ix_image_gen_jobs_status_created_at", "status", "created_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "paper_id": self.paper_id,
            "prompt": self.prompt,
            "status": self.status,
            "worker": self.worker,
            "error": self.error,
            "retry_count": self.retry_count or 0,
            "target_path": self.target_path,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "image": self.image.to_dict() if self.image else None,
        }


# ─── User State (key-value persistence) ──────────────────────────────────────
# Generic key-value store for per-user, per-paper tool/UI state.
# Replaces scattered localStorage usage with server-side persistence
# so state survives refresh, device switch, and is isolated per-user.
class UserState(db.Model):
    __tablename__ = "user_states"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    paper_id = db.Column(db.String(20), db.ForeignKey("papers.id", ondelete="CASCADE"), nullable=True)
    state_key = db.Column(db.String(100), nullable=False)
    state_value = db.Column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
    )
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        db.UniqueConstraint("user_id", "paper_id", "state_key", name="uq_user_state"),
    )

    def to_dict(self):
        return {
            "key": self.state_key,
            "paper_id": self.paper_id,
            "value": self.state_value,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ─── Production safeguard ────────────────────────────────────────────────────
# Wrap ``db.drop_all`` so it refuses to run against the production Postgres
# database. We had a near-disaster where a test fixture leaked into production
# (env-loading order issue) and dropped the live tables. Even with a clean
# conftest override, this is cheap insurance — flip the env-flag to override.
import os as _os

_real_drop_all = db.drop_all


def _safe_drop_all(*args, **kwargs):
    try:
        url = str(db.engine.url)
    except Exception:
        # No app context → no engine → impossible to verify; refuse.
        raise RuntimeError("db.drop_all() refused: no active app context to verify the bound DB.")
    is_sqlite = url.startswith("sqlite:")
    allow = _os.environ.get("PAPERFULL_ALLOW_DESTRUCTIVE_DB") == "1"
    if not is_sqlite and not allow:
        raise RuntimeError(
            f"db.drop_all() refused: connected DB is not sqlite ({url!r}). "
            "Set PAPERFULL_ALLOW_DESTRUCTIVE_DB=1 only when you really mean it."
        )
    return _real_drop_all(*args, **kwargs)


db.drop_all = _safe_drop_all
