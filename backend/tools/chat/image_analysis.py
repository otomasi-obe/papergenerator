"""
Image Analysis for Chat — Vision model integration (VIOLA-IMAGE).

When a user uploads an image (JPG/PNG) in the chat, this module sends it to
the configured vision model (MODELIMAGE) for analysis and returns a text
description that gets injected into the chat context.

Flow:
  1. Frontend base64-encodes the image → sends in messages payload as `images[]`
  2. Backend chat.py calls ``analyze_images()`` with the list of base64 images
  3. Each image is sent to VIOLA-IMAGE with a prompt asking for detailed analysis
  4. Results are concatenated and injected into the system prompt as context
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

log = logging.getLogger(__name__)

# Max image size: 10 MB base64 (~7.5 MB raw). Larger images are rejected.
_MAX_IMAGE_BYTES = 10 * 1024 * 1024

# Supported MIME types
_SUPPORTED_MIMES = {
    "image/jpeg", "image/jpg", "image/png", "image/gif",
    "image/webp", "image/bmp",
}

# Default analysis prompt — user can override via user message context
_DEFAULT_ANALYSIS_PROMPT = (
    "Analyze this image in detail. Describe what you see, including:\n"
    "- The main subject(s) and their characteristics\n"
    "- Any text, diagrams, charts, or data visualizations present\n"
    "- Colors, composition, and notable visual elements\n"
    "- If it's a technical/scientific image, explain the concepts shown\n\n"
    "Respond in the same language as the user's request."
)


def _validate_base64_image(b64_data: str) -> tuple[bool, str]:
    """Validate a base64-encoded image.

    Returns ``(is_valid, error_message)``.
    """
    if not b64_data:
        return False, "Empty image data"

    # Handle data URL format: "data:image/jpeg;base64,..."
    raw = b64_data
    mime = "image/jpeg"  # default
    if b64_data.startswith("data:"):
        parts = b64_data.split(",", 1)
        if len(parts) != 2:
            return False, "Invalid data URL format"
        header = parts[0]  # "data:image/jpeg;base64"
        raw = parts[1]
        if "image/" in header:
            mime = header.split(";")[0].replace("data:", "")

    if mime not in _SUPPORTED_MIMES:
        return False, f"Unsupported image type: {mime}"

    # Check size
    try:
        decoded = base64.b64decode(raw, validate=True)
    except Exception:
        return False, "Invalid base64 encoding"

    if len(decoded) > _MAX_IMAGE_BYTES:
        return False, f"Image too large ({len(decoded) / 1024 / 1024:.1f} MB, max {_MAX_IMAGE_BYTES / 1024 / 1024:.0f} MB)"

    return True, ""


def _to_data_url(b64_data: str) -> str:
    """Convert raw base64 or data URL to a proper data:image/...;base64,... URL."""
    if b64_data.startswith("data:"):
        return b64_data
    # Detect mime from magic bytes
    try:
        raw_bytes = base64.b64decode(b64_data[:32])
        if raw_bytes[:3] == b"\xff\xd8\xff":
            mime = "image/jpeg"
        elif raw_bytes[:8] == b"\x89PNG\r\n\x1a\n":
            mime = "image/png"
        elif raw_bytes[:4] == b"GIF8":
            mime = "image/gif"
        elif raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WEBP":
            mime = "image/webp"
        elif raw_bytes[:2] == b"BM":
            mime = "image/bmp"
        else:
            mime = "image/jpeg"
    except Exception:
        mime = "image/jpeg"
    return f"data:{mime};base64,{b64_data}"


def analyze_image(
    b64_data: str,
    prompt: str | None = None,
    *,
    max_tokens: int = 2048,
) -> str:
    """Analyze a single image using the vision model (VIOLA-IMAGE).

    Args:
        b64_data: Base64-encoded image (raw or data URL format).
        prompt: Optional custom analysis prompt. Defaults to _DEFAULT_ANALYSIS_PROMPT.
        max_tokens: Max tokens for the response.

    Returns:
        Text analysis of the image, or an error message on failure.
    """
    from utils.ai_tools.model_router import route_image_call

    valid, err = _validate_base64_image(b64_data)
    if not valid:
        return f"[Image analysis failed: {err}]"

    data_url = _to_data_url(b64_data)
    analysis_prompt = prompt or _DEFAULT_ANALYSIS_PROMPT

    # Build multimodal message (OpenAI vision format)
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": data_url,
                        "detail": "high",
                    },
                },
                {
                    "type": "text",
                    "text": analysis_prompt,
                },
            ],
        }
    ]

    # Retry up to 3 times for transient failures
    last_error = None
    for attempt in range(3):
        try:
            resp, model_used = route_image_call(
                messages,
                timeout=120,
                max_tokens=max_tokens,
            )
            result = resp.json()
            choices = result.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "")
                if content:
                    log.info("Image analysis completed via %s, %d chars", model_used, len(content))
                    return content
            log.warning("Image analysis returned empty response from %s (attempt %d/3)", model_used, attempt + 1)
            last_error = "model returned empty response"
            if attempt < 2:
                import time
                time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s
            continue
        except Exception as e:
            log.warning("Image analysis attempt %d/3 failed: %s", attempt + 1, str(e)[:200])
            last_error = str(e)[:200]
            if attempt < 2:
                import time
                time.sleep(2 ** attempt)
            continue
    
    # All retries exhausted
    log.error("Image analysis failed after 3 attempts: %s", last_error)
    return f"[Image analysis failed after 3 attempts: {last_error}]"


def analyze_images(
    images: list[dict],
    *,
    user_prompt: str | None = None,
) -> str:
    """Analyze multiple images and return concatenated analysis.

    Args:
        images: List of dicts, each with:
            - ``data``: Base64-encoded image data (raw or data URL)
            - ``name``: Optional filename for context
        user_prompt: Optional custom prompt applied to all images.

    Returns:
        Combined analysis text for all images, formatted as a block
        suitable for injection into the system prompt.
    """
    if not images:
        return ""

    results = []
    for i, img in enumerate(images, 1):
        b64_data = img.get("data", "")
        name = img.get("name", f"Image {i}")

        log.info("Analyzing image %d/%d: %s", i, len(images), name)
        analysis = analyze_image(b64_data, prompt=user_prompt)

        results.append(f"### 📷 {name}\n{analysis}")

    if not results:
        return ""

    header = f"## 📷 Image Analysis ({len(results)} image{'s' if len(results) > 1 else ''})\n"
    return header + "\n\n".join(results) + "\n"
