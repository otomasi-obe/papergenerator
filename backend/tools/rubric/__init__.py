"""Rubrik Soal Generator - Generate structured grading rubrics for exam questions."""
from __future__ import annotations

import json
from typing import Any, Generator

from tools.rubric.prompt import PROMPT, OPTIONS_SCHEMA


def _build_user_prompt(question: str, options: dict) -> str:
    """Build the user prompt with question and options."""
    level_schema = options.get("levels") or "4 Level (Kurang-Cukup-Baik-Sangat Baik)"
    include_notes = options.get("include_grading_notes", True)
    auto_weight = options.get("auto_weight", True)

    level_desc = {
        "4 Level (Kurang-Cukup-Baik-Sangat Baik)": (
            "4 tingkat: Kurang (1), Cukup (2), Baik (3), Sangat Baik (4)"
        ),
        "5 Level (Sangat Kurang-Kurang-Cukup-Baik-Sangat Baik)": (
            "5 tingkat: Sangat Kurang (1), Kurang (2), Cukup (3), Baik (4), Sangat Baik (5)"
        ),
    }.get(level_schema, level_schema)

    notes_instr = "Sertakan kolom 'Catatan Pengorek' untuk setiap level." if include_notes else "Jangan sertakan catatan pengorek."
    weight_instr = "Bobot otomatis dihitung AI (total 100%)." if auto_weight else "Bobot harus ditentukan manual."

    return f"""Soal:
{question}

Opsi:
- Level skema: {level_desc}
- {notes_instr}
- {weight_instr}

Format output HARUS JSON valid dengan struktur:
{{
  "question": "<soal asli>",
  "criteria": [
    {{
      "name": "<nama kriteria, mis: Pemahaman Konsep>",
      "weight": 30,
      "levels": [
        {{"name": "Kurang", "score": 1, "description": "...", "grading_notes": "..."}},
        {{"name": "Cukup", "score": 2, "description": "...", "grading_notes": "..."}},
        {{"name": "Baik", "score": 3, "description": "...", "grading_notes": "..."}},
        {{"name": "Sangat Baik", "score": 4, "description": "...", "grading_notes": "..."}}
      ]
    }}
  ],
  "bloom": ["C1", "C2", "C3", "C4"]
}}"""


def stream_rubric(question: str, options: dict) -> Generator[str, None, None]:
    """Stream rubric generation via SSE. Yields content-delta strings."""
    # Lazy import to avoid circular import
    from utils.ai_tools.ai_client import stream_chat as _ai_stream

    user_prompt = _build_user_prompt(question, options)
    messages = [
        {"role": "system", "content": PROMPT["system"]},
        {"role": "user", "content": user_prompt},
    ]
    for delta in _ai_stream(messages, heavy=False, max_tokens=4096, timeout=120):
        yield delta


def generate_rubric_sync(question: str, options: dict) -> dict[str, Any]:
    """Non-streaming rubric generation for programmatic use."""
    # Lazy import to avoid circular import
    from utils.ai_tools.ai_client import chat as _ai_chat

    user_prompt = _build_user_prompt(question, options)
    messages = [
        {"role": "system", "content": PROMPT["system"]},
        {"role": "user", "content": user_prompt},
    ]
    try:
        content, model_used = _ai_chat(messages, heavy=False, max_tokens=4096, timeout=120)
        if not content:
            return {"error": "No response from AI"}

        # Extract JSON from response
        json_start = content.find("{")
        json_end = content.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            parsed = json.loads(content[json_start:json_end])
            return parsed
        return {"error": "Failed to parse JSON from AI response", "raw": content}
    except json.JSONDecodeError as e:
        return {"error": f"JSON decode error: {e}", "raw": content if 'content' in locals() else ""}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}