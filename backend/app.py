"""
PaperFull - Backend API Server
=====================================
Flask API for AI-powered academic paper generation and DOCX export.
Supports IEEE conference paper format, Google OAuth login, PostgreSQL storage.
"""

import os
import re
import sys
import json
import uuid
import time
import logging
import threading
import importlib
from pathlib import Path
from datetime import datetime, timezone

from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS
from flask_jwt_extended import JWTManager, jwt_required, get_jwt_identity, get_jwt, verify_jwt_in_request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
from openai import OpenAI

from models import db, User, Paper, PaperImage, PaperFile, ApiUsageLog, AiJob, ImageGenJob
from auth import auth_bp, init_oauth
from admin import admin_bp
from chat import chat_bp
from papers_bp import papers_bp
from files_bp import files_bp
from images_bp import paper_images_bp, image_serve_bp
from jobs_bp import jobs_bp
from image_jobs_bp import image_jobs_bp
from slr_bp import slr_bp
from quota_bp import quota_bp

# ── Sentry / GlitchTip integration (no-op when DSN empty) ────────────────────
try:
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

    _dsn = os.getenv("GLITCHTIP_DSN", "").strip()
    if _dsn:
        sentry_sdk.init(
            dsn=_dsn,
            integrations=[FlaskIntegration(), SqlalchemyIntegration()],
            traces_sample_rate=0.05,
            send_default_pii=False,
            release=os.getenv("SENTRY_RELEASE", "dev"),
            environment=os.getenv("FLASK_ENV", "production"),
        )
except Exception:
    pass

from generate_ai_json_paper_aiotomasi import generate_paper_json
from generate_paper_chunked import generate_paper_json_chunked, GenerationCancelled
from template.IEEEgen import build_document as build_ieee_docx

# Load environment variables
load_dotenv(Path(__file__).parent.parent / ".env")
load_dotenv(Path(__file__).parent / ".env", override=True)

app = Flask(__name__)

# Trust nginx reverse proxy headers (X-Forwarded-For, X-Forwarded-Proto, etc.)
# This ensures url_for(..., _external=True) generates https:// URLs correctly
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# ─── Config ───────────────────────────────────────────────────────────────────
_db_url = os.getenv('DATABASE_URL')
if not _db_url:
    raise RuntimeError("DATABASE_URL environment variable is required. Set it in .env")
app.config['SQLALCHEMY_DATABASE_URI'] = _db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 12,
    'max_overflow': 28,
    'pool_timeout': 30,
    'pool_recycle': 1800,
    'pool_pre_ping': True,
}

_jwt_secret = os.getenv('JWT_SECRET_KEY')
if not _jwt_secret or _jwt_secret == 'change-me-in-production':
    raise RuntimeError("JWT_SECRET_KEY must be set to a secure value in .env")
app.config['JWT_SECRET_KEY'] = _jwt_secret

# JWT in httpOnly cookies (XSS-safe) + CSRF double-submit protection.
# Bearer header still accepted as a fallback so signed-URL/E2E tooling and
# legacy clients keep working during rollout.
from datetime import timedelta as _td
app.config['JWT_TOKEN_LOCATION'] = ['cookies', 'headers']
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = _td(hours=1)
app.config['JWT_REFRESH_TOKEN_EXPIRES'] = _td(days=7)
app.config['JWT_COOKIE_SECURE'] = os.getenv('JWT_COOKIE_SECURE', 'true').lower() == 'true'
app.config['JWT_COOKIE_HTTPONLY'] = True
app.config['JWT_COOKIE_SAMESITE'] = 'Lax'   # Lax keeps SSO callback redirects working
app.config['JWT_COOKIE_CSRF_PROTECT'] = True
app.config['JWT_ACCESS_CSRF_HEADER_NAME'] = 'X-CSRF-TOKEN'
app.config['JWT_REFRESH_CSRF_HEADER_NAME'] = 'X-CSRF-TOKEN'
app.config['JWT_ACCESS_COOKIE_PATH'] = '/api/'
app.config['JWT_REFRESH_COOKIE_PATH'] = '/api/auth/refresh'

_secret_key = os.getenv('SECRET_KEY')
if not _secret_key or _secret_key in ('flask-secret-key', 'change-me-in-production'):
    raise RuntimeError("SECRET_KEY must be set to a secure non-default value in .env")
app.config['SECRET_KEY'] = _secret_key

# Session cookie hardening — flask sessions are only used for OAuth state, but
# defaults are unsafe behind a reverse proxy.
app.config['SESSION_COOKIE_SECURE'] = os.getenv('SESSION_COOKIE_SECURE', 'true').lower() == 'true'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Lax (not Strict) so OAuth callback works

# Server-signed URL secret — used for generating short-lived signed image/file
# URLs that don't expose the bearer JWT in query strings or referer headers.
# Falls back to SECRET_KEY so existing deployments don't break, but it's
# recommended to set a dedicated rotating value.
app.config['SIGNED_URL_SECRET'] = os.getenv('SIGNED_URL_SECRET') or _secret_key

app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB max upload

# ─── Extensions ───────────────────────────────────────────────────────────────
CORS(app, supports_credentials=True, origins=[
    "http://localhost:1000",
    "http://localhost:5173",
    "https://paperfull.app",
    "https://www.paperfull.app",
])
db.init_app(app)
jwt = JWTManager(app)
init_oauth(app)

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["1000 per minute"],
    storage_uri=os.getenv("RATELIMIT_STORAGE_URI", "memory://"),
    strategy="fixed-window",
)

app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(papers_bp)
app.register_blueprint(files_bp)
app.register_blueprint(paper_images_bp)
app.register_blueprint(image_serve_bp)
app.register_blueprint(jobs_bp)
app.register_blueprint(image_jobs_bp)
app.register_blueprint(slr_bp)
app.register_blueprint(quota_bp)


# ─── OpenAPI / Swagger UI ─────────────────────────────────────────────────
_OPENAPI_PATH = Path(__file__).parent / "openapi.yaml"


@app.route("/api/openapi.yaml", methods=["GET"])
def openapi_yaml():
    """Serve the OpenAPI 3.1 spec as YAML."""
    if not _OPENAPI_PATH.is_file():
        return jsonify({"error": "Spec not found"}), 404
    return send_file(_OPENAPI_PATH, mimetype="application/yaml")


_SWAGGER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>PaperFull API — Swagger UI</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css" />
  <style>body { margin:0; } .topbar { display:none; }</style>
</head>
<body>
  <div id="swagger"></div>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.onload = () => {
      window.ui = SwaggerUIBundle({
        url: "/api/openapi.yaml",
        dom_id: "#swagger",
        deepLinking: true,
        withCredentials: true,
        requestInterceptor: (req) => {
          // Forward CSRF for state-changing calls so try-it-out actually works.
          const m = (document.cookie.match(/(?:^|;\\s*)csrf_access_token=([^;]+)/) || [])[1];
          if (m && /^(POST|PUT|PATCH|DELETE)$/i.test(req.method || '')) {
            req.headers['X-CSRF-TOKEN'] = decodeURIComponent(m);
          }
          return req;
        },
      });
    };
  </script>
</body>
</html>"""


@app.route("/api/docs", methods=["GET"])
def api_docs():
    """Serve Swagger UI from CDN, pointed at /api/openapi.yaml."""
    return Response(_SWAGGER_HTML, mimetype="text/html")


# ─── Security headers ────────────────────────────────────────────────────────
@app.after_request
def _security_headers(response):
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Permissions-Policy', 'geolocation=(), microphone=(), camera=()')
    response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
    # API responses should never be cached by intermediaries by default.
    if request.path.startswith('/api/'):
        response.headers.setdefault('Cache-Control', 'no-store')
    return response


# Stricter rate limit on auth endpoints to defend against credential stuffing.
limiter.limit("10 per minute")(auth_bp)

# ─── Logging Setup ────────────────────────────────────────────────────────────
LOG_FILE = Path(__file__).parent / "app.log"
from observability import init_observability  # noqa: E402  (after app + db ready)
init_observability(app, db, log_file=LOG_FILE)
log = logging.getLogger(__name__)

UPLOAD_FOLDER = Path(__file__).parent / "uploads"
UPLOAD_FOLDER.mkdir(exist_ok=True)
EXPORT_FOLDER = Path(__file__).parent / "exports"
EXPORT_FOLDER.mkdir(exist_ok=True)

TEMPLATE_FOLDER = Path(__file__).parent / "template"


def _available_journals():
    """Return canonical journal/template codes based on template/*.docx + *gen.py."""
    codes = []
    try:
        for docx_path in TEMPLATE_FOLDER.glob("*.docx"):
            code = docx_path.stem
            gen_path = TEMPLATE_FOLDER / f"{code}gen.py"
            if gen_path.exists():
                codes.append(code)
    except Exception:
        return []
    return sorted(set(codes), key=str.lower)


def _resolve_journal_code(raw: str | None) -> str:
    available = _available_journals()
    if not raw:
        return "IEEE" if "IEEE" in available else (available[0] if available else "IEEE")
    raw_norm = str(raw).strip()
    if not raw_norm:
        return "IEEE" if "IEEE" in available else (available[0] if available else "IEEE")

    # Case-insensitive match to avoid client-side casing bugs
    m = {c.lower(): c for c in available}
    return m.get(raw_norm.lower(), raw_norm)


def _get_builder_for_journal(journal_code: str):
    """Return the build_document callable for a known template code."""
    available = _available_journals()
    m = {c.lower(): c for c in available}
    canonical = m.get(journal_code.lower())
    if not canonical:
        raise ValueError(f"Unknown journal template: {journal_code}")
    mod = importlib.import_module(f"template.{canonical}gen")
    builder = getattr(mod, "build_document", None)
    if not callable(builder):
        raise ValueError(f"Template generator missing build_document: {canonical}gen")
    return canonical, builder

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
openai_client = None

# ─── AI Job Store (DB-backed; safe across multi-worker gunicorn) ─────────────
def _job_create(job_id: str, user_id: int, prompt: str, paper_id: str | None = None):
    """Create an AiJob row.

    ``paper_id`` is now first-class so the chat-initiated path can bind the job
    to the paper that triggered it. Frontend uses the paper_id link to:
      - resume an in-flight job after page reload
      - show the recent-done badge on the paper card
      - look up the active job from /api/papers/<paper_id>/ai-jobs/active
    Older callers that pass only 3 positional args still work because paper_id
    has a default of None.
    """
    job = AiJob(
        id=job_id,
        user_id=user_id,
        paper_id=paper_id,
        status="pending",
        prompt=prompt,
    )
    db.session.add(job)
    db.session.commit()
    return job


def _job_get(job_id: str, user_id: int):
    return AiJob.query.filter_by(id=job_id, user_id=user_id).first()


def _job_set_done(job_id: str, user_id: int, paper_data: dict, elapsed_s: int):
    job = _job_get(job_id, user_id)
    if not job:
        return
    job.status = "done"
    job.progress = 100
    job.stage = "combine"
    # Preserve the checkpoint shape (chunks_done + partial_paper) so the GET
    # handler can return paper_data via either old or new path. Falls back to
    # plain paper_data when the row was created pre-chunked.
    existing = job.result if isinstance(job.result, dict) else {}
    chunks_done = list(existing.get("chunks_done") or [])
    if "combine" not in chunks_done:
        chunks_done.append("combine")
    job.result = {
        **existing,
        "chunks_done": chunks_done,
        "partial_paper": paper_data,
        "elapsed_seconds": int(elapsed_s),
    }
    job.error = None
    job.timeout = False
    db.session.commit()


def _job_set_error(job_id: str, user_id: int, error_msg: str, timeout_flag: bool = False):
    job = _job_get(job_id, user_id)
    if not job:
        return
    job.status = "error"
    job.error = error_msg
    job.timeout = bool(timeout_flag)
    db.session.commit()

def get_openai_client():
    global openai_client
    if openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key == "sk-your-actual-api-key":
            raise Exception("OPENAI_API_KEY not configured. Please set it in .env")
        openai_client = OpenAI(api_key=api_key, timeout=1200.0)
    return openai_client

def _get_current_user_id():
    try:
        verify_jwt_in_request(optional=True)
        identity = get_jwt_identity()
        return int(identity) if identity else None
    except Exception:
        return None

def _log_api_usage(endpoint, usage, user_id=None):
    """Insert usage row + bump per-user monthly counter (token quota tracking).
    Called from a daemon thread, so it owns its own app context."""
    try:
        with app.app_context():
            log_entry = ApiUsageLog(
                user_id=user_id,
                endpoint=endpoint,
                prompt_tokens=usage.get('prompt_tokens', 0),
                completion_tokens=usage.get('completion_tokens', 0),
                total_tokens=usage.get('total_tokens', 0),
                model=OPENAI_MODEL,
            )
            db.session.add(log_entry)

            # Quota counter — reset on month change.
            if user_id is not None:
                from models import User
                u = User.query.get(int(user_id))
                if u:
                    now = datetime.now(timezone.utc)
                    month_key = now.strftime('%Y-%m')
                    if (u.usage_month_key or '') != month_key:
                        u.usage_month_key = month_key
                        u.token_used_month = 0
                    u.token_used_month = (u.token_used_month or 0) + int(usage.get('total_tokens', 0))

            db.session.commit()
    except Exception as e:
        log.warning("Failed to log API usage: %s", e)

# ─── DB Init ──────────────────────────────────────────────────────────────────
with app.app_context():
    db.create_all()
    log.info("Database tables created/verified")


# ─── AiJob sweeper (mark stuck pending jobs as errored) ──────────────────────
AIJOB_PENDING_TIMEOUT_SECONDS = 15 * 60  # 15 minutes


def _sweep_stuck_jobs():
    """Best-effort: mark AiJob rows stuck in 'pending' beyond the timeout
    as errored so the frontend stops polling forever after a worker crash.
    Runs in-process from a daemon thread; safe under multi-worker because the
    UPDATE is conditional on status='pending'.
    """
    while True:
        try:
            time.sleep(60)
            with app.app_context():
                cutoff = datetime.now(timezone.utc) - __import__('datetime').timedelta(seconds=AIJOB_PENDING_TIMEOUT_SECONDS)
                stuck = AiJob.query.filter(
                    AiJob.status == 'pending',
                    AiJob.started_at < cutoff,
                ).all()
                if not stuck:
                    continue
                for j in stuck:
                    j.status = 'error'
                    j.error = f"Job stuck >{AIJOB_PENDING_TIMEOUT_SECONDS//60}min — worker likely crashed"
                    j.timeout = True
                db.session.commit()
                log.warning("Swept %d stuck AI jobs", len(stuck))
        except Exception:
            log.exception("AiJob sweeper iteration failed")


threading.Thread(target=_sweep_stuck_jobs, daemon=True, name="aijob-sweeper").start()

# ─── Image generation worker pool (4 workers, 1 per Gemini account) ──────
# Lazy-started so the import-only path (CLI / tests / migrations) doesn't try
# to spin up Playwright. Started here on app boot.
try:
    from image_worker import start_image_workers as _start_image_workers  # noqa: PLC0415
    _start_image_workers(app)
except Exception:
    log.exception("Failed to start image worker pool — generate-image will not work")

# ─── SLR worker pool (max 10 workers, FIFO DB-backed queue) ─────────────
# Pulls SlrJob rows and runs the multi-source academic search + AI
# summarization pipeline. Idempotent across gunicorn worker processes.
# Skipped under TESTING so unit tests don't spin up the executor / pump.
if not app.config.get("TESTING"):
    try:
        from slr_worker import start_slr_workers as _start_slr_workers  # noqa: PLC0415
        _start_slr_workers(app)
    except Exception:
        log.exception("Failed to start SLR worker pool — Literature/SLR jobs will queue but not run")

# ─── Health Check ────────────────────────────────────────────────────────────

@app.route("/api/health", methods=["GET"])
@limiter.exempt
def health():
    return jsonify({
        "status": "ok",
        "model": OPENAI_MODEL,
        "timestamp": datetime.now().isoformat()
    })

# ─── AI Generate (Section) ───────────────────────────────────────────────────

@app.route("/api/generate", methods=["POST"])
@limiter.limit("20 per minute")   # AI calls are expensive; 20/min per IP
@jwt_required()
def generate():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        prompt = data.get("prompt", "")
        last_text = data.get("lastText", "")
        paper_context = data.get("paperContext", {})
        section = data.get("section", "").lower()

        if not prompt:
            return jsonify({"error": "Prompt is required"}), 400

        client = get_openai_client()

        prompts_by_section = {
            "title": "You are an IEEE conference paper title writer. Generate a concise, specific paper title (max 15 words). Return ONLY the title.",
            "abstract": "You are an IEEE conference paper writer. Generate a 150-200 word abstract. Start with problem statement, then method, then results. Return ONLY the abstract text.",
            "introduction": "You are an IEEE conference researcher. Write an INTRODUCTION section (200-300 words): 1) Motivate the problem 2) Identify research gap 3) State contributions. Include citations as [1], [2].",
            "methodology": "You are a systems researcher. Write a METHODOLOGY section describing: 1) Problem formulation 2) Proposed method/algorithm 3) Implementation details. Use IEEE notation.",
            "results": "You are a research scientist. Write EXPERIMENTAL RESULTS: 1) Datasets used 2) Metrics with values 3) Comparison with baselines 4) Analysis.",
            "conclusion": "You are an academic writer. Write CONCLUSION (100-150 words): 1) Summarize contributions 2) Highlight metrics 3) Future work.",
            "acknowledgment": "Write 2-3 sentences of paper acknowledgments thanking funding agencies, collaborators. Professional and concise.",
        }

        system_prompt = prompts_by_section.get(section,
            "You are an expert academic writer for IEEE papers. Generate content for the specified section. Use LaTeX notation for formulas. Return ONLY the content.")

        messages = [{"role": "system", "content": system_prompt}]
        context_parts = []
        if paper_context:
            context_parts.append(f"Paper title: {paper_context.get('title', 'Untitled')}")
            if paper_context.get('abstract'):
                context_parts.append(f"Abstract: {paper_context['abstract'][:500]}")
        if last_text:
            context_parts.append(f"\n--- Current content ---\n{last_text}\n--- End ---")
        if context_parts:
            messages.append({"role": "user", "content": "\n".join(context_parts)})
            messages.append({"role": "assistant", "content": "I understand the context. What would you like me to do?"})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(model=OPENAI_MODEL, messages=messages)
        result = response.choices[0].message.content
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens
        }
        user_id = _get_current_user_id()
        threading.Thread(target=_log_api_usage, args=("generate", usage, user_id), daemon=True).start()
        return jsonify({"success": True, "content": result, "model": OPENAI_MODEL, "usage": usage})

    except Exception as e:
        log.exception("unhandled error")
        return jsonify({"error": str(e)}), 500

# ─── Generate Full Paper ─────────────────────────────────────────────────────

def _run_generate_full_job(job_id, prompt, user_id=None, topic=None, style=None, pdf_texts=None, custom_prompt=None, paper_id=None, chunked=True, model=None, resume_state=None):
    t_start = time.time()
    log.info("[job:%s] started, prompt=%r, chunked=%s", job_id, prompt[:80], chunked)
    log.info("[job:%s] model=%s", job_id, model or "<env>")
    uid = None
    try:
        uid = int(user_id) if user_id is not None else None
    except Exception:
        uid = None

    # ── checkpoint + cancel wiring ─────────────────────────────────────────
    # The checkpoint sink writes partial paper progress to AiJob.result and
    # publishes the same payload to Redis so SSE subscribers (jobs_bp.stream)
    # see live updates. Cancellation is signalled by the user/UI flipping
    # AiJob.status to 'cancelled' (jobs_bp.cancel_job sets that), which we
    # poll inside the chunked orchestrator.
    def _make_checkpoint_cb(_job_id):
        def _cb(stage, progress, partial):
            try:
                with app.app_context():
                    j = AiJob.query.filter_by(id=_job_id).first()
                    if not j:
                        return
                    j.stage = stage
                    j.progress = max(0, min(100, int(progress)))
                    # AiJob.result is the canonical resume payload — chunks_done
                    # + partial_paper let /resume re-feed exactly the same shape
                    # back into generate_paper_json_chunked(resume_state=...).
                    existing = j.result if isinstance(j.result, dict) else {}
                    chunks_done = list(existing.get("chunks_done") or [])
                    if stage and stage not in chunks_done:
                        chunks_done.append(stage)
                    j.result = {
                        **existing,
                        "chunks_done": chunks_done,
                        "partial_paper": partial,
                        "last_stage": stage,
                        "last_progress": int(progress),
                    }
                    db.session.commit()
            except Exception:
                try:
                    db.session.rollback()
                except Exception:
                    pass
                log.exception("[job:%s] checkpoint_cb failed at stage=%s", _job_id, stage)

            # Best-effort SSE publish (no Redis = silent no-op).
            try:
                from jobs_bp import publish_progress
                publish_progress(_job_id, {
                    "stage": stage,
                    "percent": int(progress),
                    "status": "running",
                })
            except Exception:
                pass
        return _cb

    def _make_cancel_check(_job_id):
        def _check():
            try:
                with app.app_context():
                    j = AiJob.query.filter_by(id=_job_id).first()
                    return bool(j and j.status == "cancelled")
            except Exception:
                return False
        return _check

    checkpoint_cb = _make_checkpoint_cb(job_id) if chunked else None
    cancel_check = _make_cancel_check(job_id) if chunked else None

    try:
        api_key = os.getenv("AIOTOMASI_APIKEY")
        if not api_key:
            raise Exception("AIOTOMASI_APIKEY not configured")

        extra_parts = []
        if custom_prompt:
            extra_parts.append(custom_prompt)
        if pdf_texts:
            combined = "\n\n".join(pdf_texts[:5])
            extra_parts.append(f"[REFERENCE DOCUMENTS]\n{combined}")
        extra = ("\n\n".join(extra_parts)).strip()

        # Use chunked generation by default to avoid 30s gateway timeouts
        if chunked:
            paper_data = generate_paper_json_chunked(
                judul=prompt,
                custom_prompt=extra,
                topic=topic,
                style=style,
                model=model,
                checkpoint_cb=checkpoint_cb,
                cancel_check=cancel_check,
                resume_state=resume_state,
            )
        else:
            paper_data = generate_paper_json(
                judul=prompt,
                custom_prompt=extra,
                topic=topic,
                style=style,
                model=model,
            )

        paper_data.setdefault("authors", [{"name": "Author Name", "affiliation": "Department, University", "location": "City, Country", "email": "author@example.com"}])
        paper_data.setdefault("keywords", [])
        paper_data.setdefault("sections", [])
        paper_data.setdefault("acknowledgment", "")
        paper_data.setdefault("references", [])
        paper_data.setdefault("figures", [])
        paper_data.setdefault("tables", [])
        paper_data.setdefault("equations", [])

        for auth in paper_data["authors"]:
            auth.setdefault("name", ""); auth.setdefault("affiliation", "")
            auth.setdefault("location", ""); auth.setdefault("email", "")

        for i, sec in enumerate(paper_data["sections"]):
            sec.setdefault("id", f"id-sec{i+1}"); sec.setdefault("number", "")
            sec.setdefault("title", ""); sec.setdefault("content", "")
            sec.setdefault("subsections", [])
            for j, sub in enumerate(sec["subsections"]):
                sub.setdefault("id", f"id-sub{i+1}{chr(97+j)}")
                sub.setdefault("letter", chr(65 + j))
                sub.setdefault("title", ""); sub.setdefault("content", "")
                sub.setdefault("numberedItems", [])

        for i, fig in enumerate(paper_data["figures"]):
            fig.setdefault("id", f"figure-{i+1}"); fig.setdefault("caption", f"Fig. {i+1}. ")
            fig.setdefault("filename", ""); fig.setdefault("url", "")

        for i, tbl in enumerate(paper_data["tables"]):
            tbl.setdefault("id", f"table-{i+1}"); tbl.setdefault("caption", f"TABLE {i+1}. ")
            tbl.setdefault("headers", []); tbl.setdefault("rows", [])

        for i, eq in enumerate(paper_data["equations"]):
            eq.setdefault("id", f"eq-{i+1}"); eq.setdefault("latex", ""); eq.setdefault("number", i + 1)

        try:
            output_dir = Path(__file__).parent / "output"
            output_dir.mkdir(exist_ok=True)
            safe_title = re.sub(r"[^a-zA-Z0-9_]", "_", prompt[:50]).strip("_")
            ts_str = time.strftime("%Y%m%d_%H%M%S")
            json_out = output_dir / f"{ts_str}_{safe_title}.json"
            json_out.write_text(json.dumps(paper_data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as save_err:
            log.warning("[job:%s] Could not save JSON: %s", job_id, save_err)

        elapsed = time.time() - t_start
        _log_api_usage("generate-full", {"total_tokens": 0, "prompt_tokens": 0, "completion_tokens": 0}, user_id)
        with app.app_context():
            # Persist into Paper.data when chat-tool flow gave us a paper_id —
            # this prevents the result being lost if the one-shot /api/job
            # response is consumed before the editor reloads the paper.
            if paper_id and uid is not None:
                try:
                    paper = Paper.query.filter_by(id=paper_id, user_id=uid).first()
                    if paper:
                        paper.data = paper_data
                        paper.title = (
                            paper_data.get("title")
                            or (paper_data.get("data") or {}).get("title")
                            or paper.title
                            or "Untitled"
                        )
                        paper.updated_at = datetime.now(timezone.utc)
                        db.session.commit()
                        log.info("[job:%s] persisted into paper %s", job_id, paper_id)
                except Exception:
                    db.session.rollback()
                    log.exception("[job:%s] failed to persist into paper %s", job_id, paper_id)
            if uid is not None:
                _job_set_done(job_id, uid, paper_data, int(elapsed))
        log.info("[job:%s] DONE in %.1fs", job_id, elapsed)

    except GenerationCancelled as gc:
        # Cooperative cancel: persist whatever was already checkpointed and
        # mark the job cancelled (so the UI bubble can surface the partial
        # result + a Resume button).
        elapsed = time.time() - t_start
        log.info("[job:%s] CANCELLED at stage=%s after %.1fs", job_id, gc.stage, elapsed)
        with app.app_context():
            try:
                j = AiJob.query.filter_by(id=job_id).first()
                if j:
                    j.status = "cancelled"
                    j.stage = gc.stage
                    existing = j.result if isinstance(j.result, dict) else {}
                    j.result = {
                        **existing,
                        "cancelled_at_stage": gc.stage,
                        "elapsed_seconds": int(elapsed),
                    }
                    db.session.commit()
            except Exception:
                db.session.rollback()
                log.exception("[job:%s] failed to persist cancellation", job_id)
        try:
            from jobs_bp import publish_progress
            publish_progress(job_id, {"stage": gc.stage, "status": "cancelled"})
        except Exception:
            pass

    except Exception as e:
        elapsed = time.time() - t_start
        err_str = str(e)
        timeout_flag = "timeout" in type(e).__name__.lower() or "timeout" in err_str.lower() or "timed out" in err_str.lower()
        log.error("[job:%s] FAILED after %.1fs: %s", job_id, elapsed, e, exc_info=True)
        with app.app_context():
            if uid is not None:
                _job_set_error(
                    job_id,
                    uid,
                    f"Generation timed out after {int(elapsed)}s. Try a shorter topic." if timeout_flag else err_str,
                    timeout_flag=timeout_flag,
                )
    finally:
        # Always clear the chat-side active-job registry so the
        # /active-job endpoint stops reporting an in-flight job whether
        # generation succeeded or failed.
        try:
            from chat import clear_active_job
            if paper_id:
                clear_active_job(paper_id)
        except Exception:
            pass


@app.route("/api/papers/<paper_id>/active-job", methods=["GET"])
@jwt_required()
def get_paper_active_job(paper_id):
    """Return the active generation job for this paper, or null."""
    user_id = _get_current_user_id()
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return jsonify({"error": "Paper not found"}), 404
    try:
        from chat import _active_jobs_by_paper
        job_id = _active_jobs_by_paper.get(paper_id)
        if not job_id:
            return jsonify({"active": False})
        job = AiJob.query.filter_by(id=job_id, user_id=int(user_id)).first()
        if not job or job.status != 'pending':
            # Stale — clean up and report no active job.
            _active_jobs_by_paper.pop(paper_id, None)
            return jsonify({"active": False})
        elapsed = (
            int((datetime.now(timezone.utc) - job.started_at.replace(tzinfo=timezone.utc)).total_seconds())
            if job.started_at else 0
        )
        return jsonify({
            "active": True,
            "job_id": job.id,
            "prompt": (job.prompt or "")[:200],
            "elapsed_seconds": elapsed,
            "status": job.status,
        })
    except Exception as e:
        return jsonify({"active": False, "error": str(e)})


@app.route("/api/generate-full", methods=["POST"])
@limiter.limit("10 per minute")   # Full paper generation: heavier, stricter limit
@jwt_required()
def generate_full():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        prompt = data.get("prompt", "").strip()
        if not prompt:
            return jsonify({"error": "Prompt is required"}), 400
        topic = data.get("topic") or None
        style = data.get("style") or None
        pdf_texts = data.get("pdf_texts") or []
        model = data.get("model") or None
        if model is not None:
            allowed_models = {"V-OPUS", "V-CLAUDE", "V-GPT", "V-GLM", "V-DEEPSEEK"}
            if model not in allowed_models:
                return jsonify({"error": f"Invalid model. Allowed: {sorted(allowed_models)}"}), 400

        api_key = os.getenv("AIOTOMASI_APIKEY")
        if not api_key:
            raise Exception("AIOTOMASI_APIKEY not configured")

        user_id = _get_current_user_id()
        if not user_id:
            return jsonify({"error": "Unauthorized"}), 401
        job_id = uuid.uuid4().hex[:12]
        _job_create(job_id, int(user_id), prompt)
        threading.Thread(
            target=_run_generate_full_job,
            args=(job_id, prompt, user_id),
            kwargs={"topic": topic, "style": style, "pdf_texts": pdf_texts, "model": model},
            daemon=True,
        ).start()
        return jsonify({"success": True, "job_id": job_id})

    except Exception as e:
        log.exception("unhandled error")
        return jsonify({"error": str(e)}), 500


@app.route("/api/job/<job_id>", methods=["GET"])
@jwt_required()
def get_job_status(job_id):
    user_id = int(get_jwt_identity())
    job = _job_get(job_id, user_id)
    if job is None:
        return jsonify({"error": "Job not found or already retrieved"}), 404

    elapsed = int((datetime.now(timezone.utc) - (job.started_at.replace(tzinfo=timezone.utc) if job.started_at and job.started_at.tzinfo is None else (job.started_at or datetime.now(timezone.utc)))).total_seconds())
    if job.status == "pending":
        return jsonify({"status": "pending", "elapsed": elapsed})
    # Don't delete the row on done/error any more — the badge inbox
    # (/api/me/ai-jobs/recent) and the active-job lookup both need the row to
    # stay around. Cleanup of stale rows is handled by a future cron sweep.
    if job.status == "done":
        paper = (job.result or {}).get("partial_paper") or job.result or {}
        # Backwards-compat: legacy callers expected the full paper dict here.
        # The chunked path stores the canonical paper under partial_paper at
        # the final 'combine' checkpoint; older legacy path stored the dict
        # directly. Both shapes are tolerated.
        if isinstance(paper, dict) and "sections" not in paper and isinstance(job.result, dict):
            paper = job.result
        return jsonify({"status": "done", "success": True, "paper": paper, "usage": {}, "elapsed": elapsed})

    err = job.error or "Unknown error"
    timeout_flag = bool(job.timeout)
    return jsonify({"status": "error", "error": err, "timeout": timeout_flag})

# ─── Topics / Styles / PDF Upload ─────────────────────────────────────────────

@app.route("/api/topics", methods=["GET"])
def list_topics():
    """Return sorted list of available topic slugs."""
    topic_dir = Path(__file__).parent / "prompt" / "topic"
    topics = sorted(
        p.stem for p in topic_dir.glob("*.txt") if not p.stem.startswith("_")
    )
    return jsonify({"topics": topics})


@app.route("/api/styles", methods=["GET"])
def list_styles():
    """Return sorted list of available citation style slugs."""
    style_dir = Path(__file__).parent / "prompt" / "style"
    styles = sorted(p.stem for p in style_dir.glob("*.txt"))
    return jsonify({"styles": styles})


MAX_PDF_FILES = 10
MAX_WORDS_PER_FILE = 5000

@app.route("/api/upload-pdfs", methods=["POST"])
@limiter.limit("20 per minute")
@jwt_required()
def upload_pdfs():
    """Extract text from up to 5 uploaded PDF/DOCX files (max 5000 words each).

    Routes through the shared 20-worker extraction pool in files_bp so a chat
    upload doesn't block a Files-tab upload (and vice versa).
    """
    from extract_pdfs import extract_text_from_pdf  # noqa: PLC0415
    from docx import Document  # noqa: PLC0415
    from files_bp import _EXTRACT_POOL  # noqa: PLC0415
    import io  # noqa: PLC0415

    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "No files uploaded"}), 400
    if len(files) > MAX_PDF_FILES:
        return jsonify({"error": f"Max {MAX_PDF_FILES} files allowed"}), 400

    # Read bytes synchronously (cheap), then extract in parallel.
    payloads = []
    warnings = []
    for f in files:
        filename = (f.filename or "").lower()
        try:
            data = f.stream.read()
        except Exception as e:
            warnings.append(f"{f.filename}: gagal baca stream ({e})")
            continue
        if filename.endswith(".pdf"):
            payloads.append(("pdf", f.filename, data))
        elif filename.endswith(".docx") or filename.endswith(".doc"):
            payloads.append(("docx", f.filename, data))
        else:
            warnings.append(f"{f.filename}: format tidak didukung (hanya PDF dan DOCX)")

    def _extract(kind, name, blob):
        try:
            if kind == "pdf":
                return extract_text_from_pdf(io.BytesIO(blob))
            doc = Document(io.BytesIO(blob))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception as e:
            return f"[Error reading {name}: {e}]"

    futures = [(name, _EXTRACT_POOL.submit(_extract, kind, name, blob))
               for kind, name, blob in payloads]

    results = []
    for name, fut in futures:
        try:
            text = fut.result(timeout=120)
        except Exception as e:
            warnings.append(f"{name}: gagal mengekstrak ({e})")
            continue
        words = text.split()
        if len(words) > MAX_WORDS_PER_FILE:
            warnings.append(f"{name}: file terlalu besar, dibatasi ke {MAX_WORDS_PER_FILE} kata")
            text = " ".join(words[:MAX_WORDS_PER_FILE])
        results.append(text)

    return jsonify({"pdf_texts": results, "warnings": warnings})


# ─── Paper Files (PDF/DOCX/DOC/TXT/MD) ────────────────────────────────────
# Moved to files_bp.py — registered above.

# ─── Paper-specific Image Upload + signed URLs + image serving ───────────
# Moved to images_bp.py — registered above (paper_images_bp + image_serve_bp).

_PAPER_ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
_FILENAME_RE = re.compile(r'^[A-Za-z0-9_.-]{1,128}$')


@app.route("/api/journals", methods=["GET"])
@jwt_required()
def list_journals():
    try:
        return jsonify({"journals": _available_journals()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─── Legacy Image Upload ──────────────────────────────────────────────────────

@app.route("/api/upload-image", methods=["POST"])
@limiter.limit("30 per minute")
@jwt_required()
def upload_image_legacy():
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400
        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No file selected"}), 400
        ext = Path(file.filename).suffix.lower()
        allowed_image_exts = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
        if ext not in allowed_image_exts:
            return jsonify({"error": "Invalid image format"}), 400
        head = file.stream.read(16)
        file.stream.seek(0)
        if not _is_image_bytes(head, ext):
            return jsonify({"error": "Invalid image file"}), 400
        legacy_dir = UPLOAD_FOLDER / "legacy"
        legacy_dir.mkdir(exist_ok=True)
        filename = f"{uuid.uuid4().hex}{ext}"
        filepath = legacy_dir / filename
        file.save(str(filepath))
        return jsonify({"success": True, "filename": filename, "url": f"/api/images/legacy/{filename}", "originalName": file.filename[:255]})
    except Exception as e:
        log.exception("unhandled error")
        return jsonify({"error": str(e)}), 500

# ─── Export DOCX ──────────────────────────────────────────────────────────────

@app.route("/api/export", methods=["POST"])
@jwt_required()
def export_docx():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No paper data provided"}), 400
        paper = data.get("paper", data)

        journal_raw = data.get("journal")
        if isinstance(paper, dict) and not journal_raw:
            journal_raw = paper.get("journal")
        journal_code = _resolve_journal_code(journal_raw)
        try:
            canonical_journal, builder = _get_builder_for_journal(journal_code)
        except Exception as e:
            return jsonify({"error": str(e), "available": _available_journals()}), 400

        json_filename = f"_tmp_{uuid.uuid4().hex[:8]}.json"
        json_filepath = EXPORT_FOLDER / json_filename
        json_filepath.write_text(json.dumps(paper, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            output_path = EXPORT_FOLDER / f"{canonical_journal}_{uuid.uuid4().hex[:8]}.docx"
            builder(json_filepath, output_path)

            safe_title = re.sub(r'[^a-zA-Z0-9_\-]+', '_', str(paper.get('title', 'paper'))).strip('_')
            if not safe_title:
                safe_title = 'paper'
            download_name = f"{canonical_journal}_{safe_title[:60]}.docx"
            response = send_file(
                str(output_path), as_attachment=True,
                download_name=download_name,
                mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            @response.call_on_close
            def _cleanup():
                try:
                    output_path.unlink(missing_ok=True)
                except Exception:
                    pass
            return response
        finally:
            json_filepath.unlink(missing_ok=True)
    except Exception as e:
        log.exception("unhandled error")
        return jsonify({"error": str(e)}), 500

# ─── Paper CRUD ───────────────────────────────────────────────────────────────
# Moved to papers_bp.py — registered above. Keeping this header as a breadcrumb.

# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", os.getenv("BACKEND_PORT", 1001)))
    debug = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    log.info("=" * 60)
    log.info("PaperFull API starting on port %d", port)
    print(f"🚀 PaperFull API running on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=False, threaded=True)
