"""
Tools Blueprint
================
Standalone AI writing tools — paraphrase, translate, humanize, detect AI,
check plagiarism, fix grammar, summarize, generate citations.

Each endpoint accepts { text, option } and streams back results via SSE.
Every AI call checks quota first and deducts tokens after completion.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import requests
from flask import Blueprint, Response, jsonify, request, stream_with_context
from flask_jwt_extended import get_jwt_identity, jwt_required

from .ai_client import chat as _ai_chat, stream_chat as _ai_stream
from utils.quota import quota_exceeded
from utils.database.models import ApiUsageLog, User, db, safe_commit

tools_api = Blueprint("tools_api", __name__)
log = logging.getLogger(__name__)

from tools.paraphrase import PROMPT as _paraphrase
from tools.translator import PROMPT as _translator
from tools.humanizer import PROMPT as _humanizer
from tools.ai_detectors import PROMPT as _detector
from tools.plagiarism import PROMPT as _plagiarism, run_plagiarism as _run_plagiarism
from tools.grammar import PROMPT as _grammar
from tools.summarize import PROMPT as _summarize

try:
    from tools.summarize.summarizer import run_summarizer as _run_summarize
except ImportError:
    _run_summarize = None

from tools.translator import run_translator as _run_translator_stream, ENGINE_LIST as _TRANSLATOR_ENGINES, LANGUAGE_LIST as _TRANSLATOR_LANGUAGES, DOMAIN_LIST as _TRANSLATOR_DOMAINS

TOOL_PROMPTS = {
    "paraphrase": _paraphrase,
    "translate": _translator,
    "humanizer": _humanizer,
    "detector": _detector,
    "plagiarism": _plagiarism,
    "summarize": _summarize,
}


def _load_grammar_ai_prompt() -> dict:
    """Load the ai-grammar prompt from tools/grammar/grammar_prompt.txt.

    The file uses [SECTION:NAME] markers; we extract SYSTEM, USER_TEMPLATE,
    and OPTIONS into a dict compatible with the other TOOL_PROMPTS entries.
    """
    prompt_file = (
        Path(__file__).resolve().parents[2]
        / "tools"
        / "grammar"
        / "grammar_prompt.txt"
    )
    if not prompt_file.exists():
        raise RuntimeError(f"grammar_prompt.txt not found at {prompt_file}")
    raw = prompt_file.read_text(encoding="utf-8")
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in raw.splitlines():
        m = re.match(r"^\[SECTION:(\w+)\]$", line.strip())
        if m:
            current = m.group(1)
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)
    return {
        "system": "\n".join(sections.get("SYSTEM", [])).strip(),
        "user_template": "\n".join(sections.get("USER_TEMPLATE", [])).strip(),
        "options": "\n".join(sections.get("OPTIONS", [])).strip(),
    }


_GRAMMAR_AI_PROMPT = _load_grammar_ai_prompt()
TOOL_PROMPTS["ai-grammar"] = _GRAMMAR_AI_PROMPT


# Program-only tool runners (no LLM call). Each takes the JSON request body
# (dict) and returns a plain dict that is emitted on the SSE stream as
# {"text": "<short label>", "result": <runner_output>}.
TOOL_RUNNERS: dict[str, Callable[[dict], dict]] = {}

STREAMING_TOOL_RUNNERS: dict[str, Callable] = {}
STREAMING_TOOL_RUNNERS["translate"] = _run_translator_stream

try:
    from tools.grammar import run_grammar_markup as _run_grammar

    TOOL_RUNNERS["grammar"] = _run_grammar
except ImportError:
    _run_grammar = None  # grammar package does not yet export run_grammar_markup

try:
    from tools.paraphrase import run_paraphrase as _run_paraphrase

    TOOL_RUNNERS["paraphrase"] = _run_paraphrase
except ImportError:
    _run_paraphrase = None  # paraphrase package does not yet export run_paraphrase escorts-free mode.

try:
    from tools.humanizer import run_humanizer as _run_humanizer

    TOOL_RUNNERS["humanizer"] = _run_humanizer
except ImportError:
    _run_humanizer = None  # humanizer package does not yet export run_humanizer


if _run_plagiarism is not None:
    TOOL_RUNNERS["plagiarism"] = _run_plagiarism

if _run_summarize is not None:
    TOOL_RUNNERS["summarize"] = _run_summarize


try:
    from tools.ai_detectors.run_detector import run_detector as _run_detector

    TOOL_RUNNERS["detector"] = _run_detector
except ImportError:
    _run_detector = None

# ── Query Planner (password-gated) ────────────────────────────────────────────

try:
    from tools.Literatur.query_planner import run_query_planner_tool as _run_qp
except ImportError:
    _run_qp = None


def _query_planner_password() -> str:
    return os.environ.get("QUERY_PLANNER_PASSWORD", "").strip()


@tools_api.route("/api/tools/query-planner", methods=["POST"])
@jwt_required()
def run_query_planner():
    """Password-gated Query Planner tool.

    Request body: { text: <topic> }  -- password already verified via /verify endpoint

    - If user's user_memory.query_planner_blocked is True → 403 "maintenance"
    - Run planner and return result
    """
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)

    # ── Check if user is already blocked ──
    mem = dict(user.user_memory or {})
    if mem.get("query_planner_blocked"):
        return jsonify({"error": "Tool under maintenance for your account", "blocked": True}), 403

    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()

    if not text:
        return jsonify({"error": "No topic provided"}), 400

    # ── Quota check ──
    exceeded, info = quota_exceeded(user_id)
    if exceeded:
        return jsonify({"error": "Kuota token habis", **info}), 429

    # ── Run planner ──
    if _run_qp is None:
        return jsonify({"error": "Query planner module not available"}), 500
    try:
        result = _run_qp(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        log.exception("query-planner failed for user=%d", user_id)
        return jsonify({"error": f"Tool failed: {type(e).__name__}: {e}"}), 500

    # Estimate and log tokens
    result_text = json.dumps(result)
    _log_tool_usage(user_id, "query-planner", "runner/query-planner",
                    _estimate_tokens(text), _estimate_tokens(result_text))

    return jsonify({"result": result})


@tools_api.route("/api/tools/query-planner/verify", methods=["POST"])
@jwt_required()
def query_planner_verify():
    """Verify password before revealing the Query Planner UI."""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    mem = dict(user.user_memory or {})
    if mem.get("query_planner_blocked"):
        return jsonify({"error": "Tool under maintenance for your account", "blocked": True}), 403

    data = request.get_json(silent=True) or {}
    pw = (data.get("password") or "").strip()
    if not pw or pw != _query_planner_password():
        mem["query_planner_blocked"] = True
        user.user_memory = mem
        safe_commit()
        log.warning("QP_BLOCKED user=%d wrong/missing password on verify", user_id)
        return jsonify({"error": "Incorrect password — tool locked for your account", "blocked": True}), 403

    return jsonify({"ok": True})


@tools_api.route("/api/tools/query-planner/status", methods=["GET"])
@jwt_required()
def query_planner_status():
    """Check if query-planner is blocked for current user."""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    mem = user.user_memory or {}
    return jsonify({
        "blocked": mem.get("query_planner_blocked", False),
        "requires_password": bool(_query_planner_password()),
    })


@tools_api.route("/api/tools/query-planner/unblock", methods=["POST"])
@jwt_required()
def query_planner_unblock():
    """Admin-only: unblock a user's query-planner access."""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if user.role != "admin":
        return jsonify({"error": "Admin only"}), 403

    data = request.get_json(silent=True) or {}
    target_id = data.get("user_id")
    if not target_id:
        return jsonify({"error": "user_id required"}), 400

    target = User.query.get(int(target_id))
    if not target:
        return jsonify({"error": "User not found"}), 404

    mem = dict(target.user_memory or {})
    mem["query_planner_blocked"] = False
    target.user_memory = mem
    safe_commit()
    log.info("QP_UNBLOCK admin=%d target=%d", user_id, target_id)
    return jsonify({"ok": True, "user_id": target_id})


# ── Token tracking helpers ────────────────────────────────────────────────────

def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English/Indonesian mix."""
    return max(1, len(text) // 4)


def _log_tool_usage(
    user_id: int,
    tool_id: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
):
    """Log token usage and deduct from user's monthly quota."""
    try:
        total = prompt_tokens + completion_tokens
        if total <= 0:
            return

        log_entry = ApiUsageLog(
            user_id=user_id,
            endpoint=f"/api/tools/{tool_id}",
            model=model or "tools",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            created_at=datetime.now(timezone.utc),
        )
        db.session.add(log_entry)

        user = User.query.get(int(user_id))
        if user and user.role != "admin":
            now = datetime.now(timezone.utc)
            month_key = now.strftime("%Y-%m")
            if (user.usage_month_key or "") != month_key:
                user.usage_month_key = month_key
                user.token_used_month = 0
            user.token_used_month = int(user.token_used_month or 0) + total

        safe_commit()
        log.info(
            "TOKEN_DEDUCT user=%d tool=%s model=%s prompt=%d completion=%d total=%d",
            user_id, tool_id, model or "tools", prompt_tokens, completion_tokens, total,
        )
    except Exception as e:
        log.warning("TOKEN_DEDUCT_FAILED user=%d tool=%s: %s", user_id, tool_id, e)


# ── Streaming / non-streaming AI wrappers with token tracking ─────────────────

def _stream_ai(system_prompt, user_prompt, user_id=None, tool_id=None):
    """Stream AI response via SSE. After stream completes, log token usage."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    accumulated = ""
    try:
        for delta in _ai_stream(messages, heavy=False, max_tokens=4096, timeout=120):
            accumulated += delta
            yield f"data: {json.dumps({'text': delta})}\n\n"
    except GeneratorExit:
        log.info("_stream_ai: client disconnected mid-stream")
        return
    except RuntimeError as e:
        if "no endpoint configured" in str(e):
            yield f"data: {json.dumps({'error': 'AI service not configured'})}\n\n"
        else:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        return
    except requests.exceptions.Timeout:
        yield f"data: {json.dumps({'error': 'AI service timeout'})}\n\n"
        return
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
        return

    # Stream completed — log token usage
    if user_id and tool_id:
        prompt_tokens = _estimate_tokens(system_prompt + user_prompt)
        completion_tokens = _estimate_tokens(accumulated)
        _log_tool_usage(user_id, tool_id, "stream", prompt_tokens, completion_tokens)


def _non_stream_ai(system_prompt, user_prompt, user_id=None, tool_id=None):
    """Non-streaming AI call for detector/plagiarism that need JSON results."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    try:
        content, model_used = _ai_chat(messages, heavy=False, max_tokens=2048, timeout=60)
        if not content:
            return {"error": "No response from AI"}

        # Log token usage (estimate since upstream usage not returned)
        if user_id and tool_id:
            prompt_t = _estimate_tokens(system_prompt + user_prompt)
            comp_t = _estimate_tokens(content)
            _log_tool_usage(user_id, tool_id, model_used, prompt_t, comp_t)

        return {"text": content}
    except RuntimeError as e:
        if "no endpoint configured" in str(e):
            return {"error": "AI service not configured"}
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}


@tools_api.route("/api/tools/<tool_id>", methods=["POST"])
@jwt_required()
def run_tool(tool_id):
    user_id = get_jwt_identity()
    if not user_id:
        return Response(
            f"data: {json.dumps({'error': 'Unauthorized'})}\n\n",
            status=401,
            mimetype="text/event-stream",
        )

    # ── Quota check (skip for admin) ──
    exceeded, info = quota_exceeded(int(user_id))
    if exceeded:
        return Response(
            f"data: {json.dumps({'error': 'Kuota token habis. Silakan beli paket token untuk melanjutkan.', **info})}\n\n",
            status=429,
            mimetype="text/event-stream",
        )

    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()

    if tool_id in TOOL_RUNNERS:
        if not text:
            return Response(
                f"data: {json.dumps({'error': 'No text provided'})}\n\n",
                status=400,
                mimetype="text/event-stream",
            )
        try:
            result = TOOL_RUNNERS[tool_id](data)
        except ValueError as e:
            return Response(
                f"data: {json.dumps({'error': str(e)})}\n\n",
                status=400,
                mimetype="text/event-stream",
            )
        except Exception as e:
            log.exception("Tool runner %s failed", tool_id)
            return Response(
                f"data: {json.dumps({'error': f'Tool failed: {type(e).__name__}: {e}'})}\n\n",
                status=500,
                mimetype="text/event-stream",
            )

        # Estimate tokens for program-only runners (input + output text)
        result_text = json.dumps(result) if isinstance(result, dict) else str(result)
        prompt_tokens = _estimate_tokens(text)
        completion_tokens = _estimate_tokens(result_text)
        _log_tool_usage(int(user_id), tool_id, f"runner/{tool_id}", prompt_tokens, completion_tokens)

        # Runners may return {"text": <markup>, "result": <dict>} or just <dict>
        if isinstance(result, dict) and "text" in result and "result" in result:
            payload = result
        else:
            payload = {"text": json.dumps(result), "result": result}

        return Response(
            f"data: {json.dumps(payload)}\n\n",
            mimetype="text/event-stream",
        )

    if tool_id in STREAMING_TOOL_RUNNERS:
        if not text:
            return Response(
                f"data: {json.dumps({'error': 'No text provided'})}\n\n",
                status=400, mimetype="text/event-stream",
            )
        def _generate():
            accumulated = ""
            try:
                for chunk in STREAMING_TOOL_RUNNERS[tool_id](data):
                    # Accumulate text from streaming chunks
                    if isinstance(chunk, dict) and chunk.get("text"):
                        accumulated += chunk["text"]
                    yield f"data: {json.dumps(chunk)}\n\n"
            except Exception as e:
                log.exception("Streaming tool %s failed", tool_id)
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            finally:
                # Log token usage after stream completes
                if accumulated:
                    prompt_tokens = _estimate_tokens(text)
                    completion_tokens = _estimate_tokens(accumulated)
                    _log_tool_usage(int(user_id), tool_id, f"stream/{tool_id}", prompt_tokens, completion_tokens)
        return Response(
            stream_with_context(_generate()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    tool_config = TOOL_PROMPTS.get(tool_id)
    if not tool_config:
        return Response(
            f"data: {json.dumps({'error': f'Unknown tool: {tool_id}'})}\n\n",
            status=400,
            mimetype="text/event-stream",
        )

    option = (data.get("option") or "Standard").strip()

    if not text:
        return Response(
            f"data: {json.dumps({'error': 'No text provided'})}\n\n",
            status=400,
            mimetype="text/event-stream",
        )

    is_json_tool = tool_id in ("detector", "plagiarism")

    if is_json_tool:
        # Non-streaming for tools that return JSON results
        full_prompt = tool_config["user_template"].format(option=option, text=text)
        result = _non_stream_ai(
            tool_config["system"], full_prompt,
            user_id=int(user_id), tool_id=tool_id,
        )

        if "error" in result:
            return Response(
                f"data: {json.dumps({'error': result['error']})}\n\n",
                status=500,
                mimetype="text/event-stream",
            )

        raw_text = result.get("text", "")
        # Try to extract JSON from the response
        try:
            # Try to find JSON in the response
            json_start = raw_text.find("{")
            json_end = raw_text.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                parsed = json.loads(raw_text[json_start:json_end])
                if "pct" not in parsed:
                    parsed["pct"] = 15 if tool_id == "detector" else 8
            else:
                parsed = {"pct": 15 if tool_id == "detector" else 8, "reasons": [], "suggestions": []}
        except json.JSONDecodeError:
            parsed = {"pct": 15 if tool_id == "detector" else 8, "reasons": [], "suggestions": []}

        return Response(
            f"data: {json.dumps({'text': raw_text, 'result': parsed})}\n\n",
            mimetype="text/event-stream",
        )

    # Streaming for text-output tools
    full_prompt = tool_config["user_template"].format(option=option, text=text)

    return Response(
        stream_with_context(_stream_ai(
            tool_config["system"], full_prompt,
            user_id=int(user_id), tool_id=tool_id,
        )),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@tools_api.route("/api/tools/translate/config", methods=["GET"])
@jwt_required()
def get_translator_config():
    return jsonify({
        "engines": _TRANSLATOR_ENGINES,
        "languages": _TRANSLATOR_LANGUAGES,
        "domains": _TRANSLATOR_DOMAINS,
    })
