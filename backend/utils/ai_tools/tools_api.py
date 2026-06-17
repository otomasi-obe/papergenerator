"""
Tools Blueprint
================
Standalone AI writing tools — paraphrase, translate, humanize, detect AI,
check plagiarism, fix grammar, summarize, generate citations.

Each endpoint accepts { text, option } and streams back results via SSE.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Callable

import requests
from flask import Blueprint, Response, request, stream_with_context
from flask_jwt_extended import get_jwt_identity, jwt_required

from .ai_client import chat as _ai_chat, stream_chat as _ai_stream

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
    from tools.grammar import run_grammar as _run_grammar

    TOOL_RUNNERS["grammar"] = _run_grammar
except ImportError:
    _run_grammar = None  # grammar package does not yet export run_grammar

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


def _stream_ai(system_prompt, user_prompt):
    """Stream AI response via SSE using the per-index endpoint chain."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    try:
        for delta in _ai_stream(messages, heavy=False, max_tokens=4096, timeout=120):
            yield f"data: {json.dumps({'text': delta})}\n\n"
    except GeneratorExit:
        # Client disconnected mid-stream. Nothing to yield back — just let
        # the underlying requests stream close on its own (the context manager
        # in _ai_stream will handle it).
        log.info("_stream_ai: client disconnected mid-stream")
        return
    except RuntimeError as e:
        if "no endpoint configured" in str(e):
            yield f"data: {json.dumps({'error': 'AI service not configured'})}\n\n"
        else:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    except requests.exceptions.Timeout:
        yield f"data: {json.dumps({'error': 'AI service timeout'})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


def _non_stream_ai(system_prompt, user_prompt):
    """Non-streaming AI call for detector/plagiarism that need JSON results."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    try:
        content, _model = _ai_chat(messages, heavy=False, max_tokens=2048, timeout=60)
        if not content:
            return {"error": "No response from AI"}
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
        return Response(
            f"data: {json.dumps({'text': json.dumps(result), 'result': result})}\n\n",
            mimetype="text/event-stream",
        )

    if tool_id in STREAMING_TOOL_RUNNERS:
        if not text:
            return Response(
                f"data: {json.dumps({'error': 'No text provided'})}\n\n",
                status=400, mimetype="text/event-stream",
            )
        def _generate():
            try:
                for chunk in STREAMING_TOOL_RUNNERS[tool_id](data):
                    yield f"data: {json.dumps(chunk)}\n\n"
            except Exception as e:
                log.exception("Streaming tool %s failed", tool_id)
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
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
        result = _non_stream_ai(tool_config["system"], full_prompt)

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
        stream_with_context(_stream_ai(tool_config["system"], full_prompt)),
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
