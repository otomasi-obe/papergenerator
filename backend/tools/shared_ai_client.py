"""shared_ai_client — compatibility shim.

Historically several tools (translator, grammar/spell_checker, etc.) imported
``ai_generate`` from a module named ``shared_ai_client``. That module was
removed during a refactor but the call sites were never updated, leaving a
dangling ``ImportError`` (the standalone translator CLI could not even import).

This shim restores the symbol by delegating to the real AI client in
``utils.ai_tools.ai_client``. It lives under ``backend/tools`` so the
``sys.path`` manipulation in those tools (which appends ``backend/tools``)
resolves it without changes to the call sites.

Signature preserved:
    ai_generate(prompt, system_prompt=None, max_tokens=..., temperature=...) -> str
"""
from __future__ import annotations

from typing import Optional

from utils.ai_tools.ai_client import chat as _chat


def ai_generate(
    prompt: str,
    system_prompt: Optional[str] = None,
    max_tokens: int = 4096,
    temperature: Optional[float] = None,
    **kwargs,
) -> str:
    """Generate text via the shared AI client.

    Returns the generated text (str). Mirrors the old ``ai_generate`` contract
    that the translator/grammar call sites rely on.
    """
    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    content, _model = _chat(
        messages,
        max_tokens=max_tokens,
        temperature=temperature,
        **kwargs,
    )
    return content if content is not None else ""
