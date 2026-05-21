"""
Database Models for PaperFull
=====================================
SQLAlchemy models for users, papers, images, and API usage logs.
"""

from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSONB
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


def _utcnow():
    return datetime.now(timezone.utc)


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    google_id = db.Column(db.String(100), unique=True, nullable=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    password_hash = db.Column(db.String(255), nullable=True)
    avatar_url = db.Column(db.String(500))
    role = db.Column(db.String(20), default='user')  # 'user' or 'admin'
    created_at = db.Column(db.DateTime, default=_utcnow)
    last_login = db.Column(db.DateTime, default=_utcnow)
    # Token quota (admin-managed via /api/admin/users/<id>/quota)
    token_quota_monthly = db.Column(db.Integer, default=1000000, nullable=False)
    token_used_month = db.Column(db.Integer, default=0, nullable=False)
    usage_month_key = db.Column(db.String(7), default='')  # 'YYYY-MM'

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    papers = db.relationship('Paper', backref='user', lazy=True, cascade='all, delete-orphan')
    usage_logs = db.relationship('ApiUsageLog', backref='user', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'name': self.name,
            'avatar_url': self.avatar_url,
            'role': self.role,
            'created_at': self.created_at.isoformat(),
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'token_quota_monthly': self.token_quota_monthly,
            'token_used_month': self.token_used_month,
            'usage_month_key': self.usage_month_key,
        }


class Paper(db.Model):
    __tablename__ = 'papers'

    id = db.Column(db.String(20), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.Text, default='Untitled')
    data = db.Column(JSONB, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    images = db.relationship('PaperImage', backref='paper', lazy=True, cascade='all, delete-orphan')
    files = db.relationship('PaperFile', backref='paper', lazy=True, cascade='all, delete-orphan')
    conversations = db.relationship('Conversation', backref='paper', lazy=True, cascade='all, delete-orphan')
    memory_entries = db.relationship('ProjectMemory', backref='paper', lazy=True, cascade='all, delete-orphan')

    def to_dict(self, include_data=False):
        result = {
            'id': self.id,
            'title': self.title,
            'user_id': self.user_id,
            'image_count': len(self.images),
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }
        if include_data:
            result['data'] = self.data
        return result


class PaperImage(db.Model):
    __tablename__ = 'paper_images'

    id = db.Column(db.Integer, primary_key=True)
    paper_id = db.Column(db.String(20), db.ForeignKey('papers.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)      # stored filename (uuid-based)
    original_name = db.Column(db.String(255), nullable=False)  # original upload name
    file_path = db.Column(db.String(500), nullable=False)      # relative path in uploads/
    created_at = db.Column(db.DateTime, default=_utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'paper_id': self.paper_id,
            'filename': self.filename,
            'original_name': self.original_name,
            'url': f'/api/images/{self.paper_id}/{self.filename}',
            'created_at': self.created_at.isoformat(),
        }


class PaperFile(db.Model):
    """Generic file (pdf/docx/doc/txt/md) attached to a paper for the Files tab."""
    __tablename__ = 'paper_files'

    id = db.Column(db.Integer, primary_key=True)
    paper_id = db.Column(db.String(20), db.ForeignKey('papers.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)       # stored filename (uuid-based)
    original_name = db.Column(db.String(255), nullable=False)  # original upload name
    ext = db.Column(db.String(10), nullable=False)             # .pdf .docx etc
    size_bytes = db.Column(db.Integer, default=0)
    file_path = db.Column(db.String(500), nullable=False)      # relative path in uploads/
    extracted_text = db.Column(db.Text, default='')            # cached text for preview
    created_at = db.Column(db.DateTime, default=_utcnow)

    def to_dict(self, include_text=False):
        d = {
            'id': self.id,
            'paper_id': self.paper_id,
            'filename': self.filename,
            'original_name': self.original_name,
            'ext': self.ext,
            'size_bytes': self.size_bytes,
            'url': f'/api/papers/{self.paper_id}/files/{self.id}/raw',
            'preview_url': f'/api/papers/{self.paper_id}/files/{self.id}/preview',
            'created_at': self.created_at.isoformat(),
        }
        if include_text:
            d['text'] = self.extracted_text or ''
        return d


class ApiUsageLog(db.Model):
    __tablename__ = 'api_usage_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    endpoint = db.Column(db.String(100), nullable=False)
    prompt_tokens = db.Column(db.Integer, default=0)
    completion_tokens = db.Column(db.Integer, default=0)
    total_tokens = db.Column(db.Integer, default=0)
    model = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=_utcnow)


class Conversation(db.Model):
    """Chat thread inside a paper project. One paper can have many chats."""
    __tablename__ = 'conversations'

    id = db.Column(db.String(20), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    paper_id = db.Column(db.String(20), db.ForeignKey('papers.id'), nullable=True)
    title = db.Column(db.Text, default='New Chat')
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    messages = db.relationship('ChatMessage', backref='conversation', lazy=True, cascade='all, delete-orphan', order_by='ChatMessage.created_at')

    def to_dict(self, include_messages=False):
        result = {
            'id': self.id,
            'user_id': self.user_id,
            'paper_id': self.paper_id,
            'title': self.title,
            'message_count': len(self.messages),
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }
        if include_messages:
            result['messages'] = [m.to_dict() for m in self.messages]
        return result


class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.String(20), db.ForeignKey('conversations.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, default='')
    thinking = db.Column(db.Text, nullable=True)
    tool_calls = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'role': self.role,
            'content': self.content,
            'thinking': self.thinking,
            'tool_calls': self.tool_calls,
            'created_at': self.created_at.isoformat(),
        }


class ProjectMemory(db.Model):
    """Per-paper memory entries shared by all chats inside that paper.

    The AI saves facts here (judul tentatif, metodologi, gaya bahasa, dll) via
    the SaveMemory tool, and reads them back at the start of every conversation.
    """
    __tablename__ = 'project_memory'

    id = db.Column(db.Integer, primary_key=True)
    paper_id = db.Column(db.String(20), db.ForeignKey('papers.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    key = db.Column(db.String(120), nullable=False)
    value = db.Column(db.Text, nullable=False)
    kind = db.Column(db.String(40), default='fact')
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        db.UniqueConstraint('paper_id', 'key', name='uq_project_memory_paper_key'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'paper_id': self.paper_id,
            'key': self.key,
            'value': self.value,
            'kind': self.kind,
            'updated_at': self.updated_at.isoformat(),
        }


class AiJob(db.Model):
    __tablename__ = 'ai_jobs'

    id = db.Column(db.String(20), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    paper_id = db.Column(db.String(20), db.ForeignKey('papers.id'), nullable=True, index=True)
    kind = db.Column(db.String(30), nullable=False, default='generate_paper')
    status = db.Column(db.String(20), nullable=False, default='queued')  # queued|running|done|error|cancelled
    progress = db.Column(db.Integer, default=0)  # 0..100
    stage = db.Column(db.String(60), default='')  # 'outline' | 'sections' | 'references' | ...
    prompt = db.Column(db.Text)
    result = db.Column(db.JSON, nullable=True, default=dict)
    error = db.Column(db.Text)
    timeout = db.Column(db.Boolean, default=False)
    started_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'paper_id': self.paper_id,
            'kind': self.kind,
            'status': self.status,
            'progress': self.progress,
            'stage': self.stage,
            'error': self.error,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class LiteratureItem(db.Model):
    """One row in a paper's Literature tab.

    Bisa berasal dari hasil SLR (`source_kind='slr'`), upload PDF/DOCX
    (`source_kind='file'`), atau input manual user (`source_kind='manual'`).
    Editable via PATCH endpoint dan dipakai sebagai data sumber utk
    GenerateFullPaper.
    """
    __tablename__ = 'literature_items'

    id = db.Column(db.Integer, primary_key=True)
    paper_id = db.Column(db.String(20), db.ForeignKey('papers.id'),
                         nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    source_kind = db.Column(db.String(20), default='slr')   # slr | file | manual
    source = db.Column(db.String(40), default='')           # arxiv|ieee|sinta|...
    title = db.Column(db.Text, default='')
    authors = db.Column(db.JSON, nullable=True, default=list)  # list[str]
    year = db.Column(db.Integer, nullable=True)
    venue = db.Column(db.Text, default='')
    publisher = db.Column(db.Text, default='')
    doi = db.Column(db.String(255), nullable=True, index=True)
    url = db.Column(db.Text, default='')
    abstract = db.Column(db.Text, default='')
    summary = db.Column(db.Text, default='')
    citations = db.Column(db.Integer, nullable=True)
    score_total = db.Column(db.Float, nullable=True)
    score_breakdown = db.Column(db.JSON, nullable=True, default=dict)
    must_read = db.Column(db.Boolean, default=False)
    is_relevant = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text, default='')                  # user-editable notes
    pinned = db.Column(db.Boolean, default=False)           # user-pinned to top
    file_id = db.Column(db.Integer, db.ForeignKey('paper_files.id'),
                        nullable=True)
    slr_job_id = db.Column(db.String(20), db.ForeignKey('slr_jobs.id'),
                           nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'paper_id': self.paper_id,
            'source_kind': self.source_kind,
            'source': self.source,
            'title': self.title,
            'authors': self.authors or [],
            'year': self.year,
            'venue': self.venue,
            'publisher': self.publisher,
            'doi': self.doi,
            'url': self.url,
            'abstract': self.abstract,
            'summary': self.summary,
            'citations': self.citations,
            'score_total': self.score_total,
            'score_breakdown': self.score_breakdown or {},
            'must_read': bool(self.must_read),
            'is_relevant': bool(self.is_relevant),
            'notes': self.notes or '',
            'pinned': bool(self.pinned),
            'file_id': self.file_id,
            'slr_job_id': self.slr_job_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class SlrJob(db.Model):
    """Background SLR search job. Diproses oleh slr_worker pool (≤10 worker)."""
    __tablename__ = 'slr_jobs'

    id = db.Column(db.String(20), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'),
                        nullable=False, index=True)
    paper_id = db.Column(db.String(20), db.ForeignKey('papers.id'),
                         nullable=False, index=True)
    conversation_id = db.Column(db.String(20),
                                db.ForeignKey('conversations.id'),
                                nullable=True)
    query = db.Column(db.Text, nullable=False)
    sources = db.Column(db.JSON, nullable=True, default=list)
    top_k = db.Column(db.Integer, default=50)
    per_source = db.Column(db.Integer, default=60)
    year_from = db.Column(db.Integer, nullable=True)
    ai_summarize = db.Column(db.Boolean, default=True)
    ai_model = db.Column(db.String(40), default='V-OPUS')

    status = db.Column(db.String(20), default='queued', index=True)
    # queued|running|done|error|cancelled
    stage = db.Column(db.String(40), default='')
    progress = db.Column(db.Integer, default=0)              # 0..100
    progress_message = db.Column(db.Text, default='')
    result = db.Column(db.JSON, nullable=True, default=dict)  # full pipeline output
    error = db.Column(db.Text, default='')

    queued_at = db.Column(db.DateTime, default=_utcnow)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    def to_dict(self, include_result=False):
        stats = (self.result or {}).get('stats') if isinstance(self.result, dict) else {}
        d = {
            'id': self.id,
            'paper_id': self.paper_id,
            'conversation_id': self.conversation_id,
            'query': self.query,
            'sources': self.sources or [],
            'top_k': self.top_k,
            'status': self.status,
            'stage': self.stage,
            'progress': int(self.progress or 0),
            'progress_message': self.progress_message or '',
            'error': self.error or '',
            'queued_at': self.queued_at.isoformat() if self.queued_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'finished_at': self.finished_at.isoformat() if self.finished_at else None,
            'stats': stats or {},
        }
        if include_result:
            d['result'] = self.result or {}
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
    __tablename__ = 'image_gen_jobs'

    id = db.Column(db.String(32), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    paper_id = db.Column(db.String(20), db.ForeignKey('papers.id'), nullable=False, index=True)
    prompt = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='queued')  # queued|running|done|error
    worker = db.Column(db.String(40), nullable=True)  # which account picked it up
    image_id = db.Column(db.Integer, db.ForeignKey('paper_images.id'), nullable=True)
    error = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)

    image = db.relationship('PaperImage', foreign_keys=[image_id])

    def to_dict(self):
        return {
            'id': self.id,
            'paper_id': self.paper_id,
            'prompt': self.prompt,
            'status': self.status,
            'worker': self.worker,
            'error': self.error,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'finished_at': self.finished_at.isoformat() if self.finished_at else None,
            'image': self.image.to_dict() if self.image else None,
        }
