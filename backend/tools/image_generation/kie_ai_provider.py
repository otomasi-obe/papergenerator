"""Kie.ai image generation provider with per-family API key pool.

Usage:
    from tools.image_generation.kie_ai_provider import KieAIProvider

    provider = KieAIProvider()  # reads KIE_AI_API_KEYS / KIE_AI_API_KEY from env
    result = provider.generate(prompt="...", model="nano-banana-2-lite")
    # result: {"url": "...", "task_id": "...", "credits": 4.0, "key_used": "..."}

Key pool:
    KIE_AI_API_KEYS = "key1,key2"   (comma-separated, different accounts = different quota)
    Falls back to single KIE_AI_API_KEY if KEYS not set.
    On 402/429/433 (quota/rate limit) the provider auto-rotates to the next key.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

KIE_API_URL = "https://api.kie.ai/api/v1/jobs"
DEFAULT_MODEL = "nano-banana-2-lite"
AVAILABLE_MODELS = {
    "nano-banana-2-lite": "Nano Banana 2 Lite (fast, 4 credits)",
    "nano-banana": "Nano Banana (original)",
    "nano-banana-edit": "Nano Banana Edit (image editing)",
    "z-image": "Z-Image (Qwen, high-quality)",
}

# HTTP status / Kie.ai codes that mean "this key is exhausted" → try next key
LIMIT_CODES = {402, 429, 433}


class KieKeyExhausted(RuntimeError):
    """All keys in the pool returned quota/rate-limit errors."""


def _load_key_pool() -> list[str]:
    """Read KIE_AI_API_KEYS (comma-sep) or fall back to single KIE_AI_API_KEY."""
    raw = os.getenv("KIE_AI_API_KEYS", "").strip()
    if raw:
        keys = [k.strip() for k in raw.split(",") if k.strip()]
        if keys:
            return keys
    single = os.getenv("KIE_AI_API_KEY", "").strip()
    return [single] if single else []


class KieAIProvider:
    """Kie.ai image generation via async task polling with key rotation."""

    def __init__(
        self,
        api_key: str | None = None,
        api_keys: list[str] | None = None,
        base_url: str = KIE_API_URL,
        timeout: int = 300,
        poll_interval: float = 5.0,
    ):
        # Priority: explicit pool > explicit single > env pool (KIE_AI_KEYS_NANO/ZIMAGE) > env single (KIE_AI_API_KEY)
        if api_keys:
            self.key_pool = list(api_keys)
        elif api_key:
            self.key_pool = [api_key]
        else:
            self.key_pool = _load_key_pool()
            # If only KIE_AI_API_KEY set (no pool), use it as single-element pool
            if not self.key_pool:
                single = os.getenv("KIE_AI_API_KEY", "").strip()
                if single:
                    self.key_pool = [single]

        if not self.key_pool or not self.key_pool[0]:
            raise RuntimeError("KIE_AI_API_KEY(S) not set (env or arg)")

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.poll_interval = poll_interval

    def generate(
        self,
        prompt: str,
        out_path: str | Path,
        *,
        model: str = DEFAULT_MODEL,
        aspect_ratio: str = "1:1",
        output_format: str = "png",
        nsfw_checker: bool = True,
        compress: bool = True,
        max_size_mb: float = 1.0,
    ) -> dict:
        """Generate image and save to out_path. Auto-rotates keys on quota error."""
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        last_err: Exception | None = None
        # Try each key in pool; rotate on limit errors
        for idx, key in enumerate(self.key_pool):
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            }
            try:
                task_id = self._create_task(prompt, model, aspect_ratio, output_format, nsfw_checker, headers)
                log.info("kie_ai: task created task_id=%s model=%s key#%d", task_id, model, idx)
                result = self._poll_task(task_id, headers)
                img_url = result.get("resultUrls", [None])[0]
                if not img_url:
                    raise RuntimeError(f"No result URL in response: {result}")
                img_bytes = self._download_image(img_url)
                if compress:
                    img_bytes = self._compress_image(img_bytes, max_size_mb)
                out.write_bytes(img_bytes)
                return {
                    "url": img_url,
                    "task_id": task_id,
                    "model": model,
                    "credits": result.get("creditsConsumed"),
                    "size": len(img_bytes),
                    "local_path": str(out),
                    "key_used": f"key#{idx}",
                }
            except KieKeyExhausted as e:
                log.warning("kie_ai: key#%d exhausted (%s) — rotating", idx, e)
                last_err = e
                continue  # try next key
        # All keys exhausted
        raise RuntimeError(f"All Kie.ai keys exhausted: {last_err}")

    def _create_task(
        self,
        prompt: str,
        model: str,
        aspect_ratio: str,
        output_format: str,
        nsfw_checker: bool,
        headers: dict,
    ) -> str:
        payload = {
            "model": model,
            "input": {
                "prompt": prompt,
                "output_format": output_format,
                "aspect_ratio": aspect_ratio,
                "nsfw_checker": nsfw_checker,
            },
        }
        with httpx.Client(timeout=30) as client:
            resp = client.post(f"{self.base_url}/createTask", headers=headers, json=payload)
        if resp.status_code in LIMIT_CODES:
            raise KieKeyExhausted(f"HTTP {resp.status_code}: {resp.text[:200]}")
        if resp.status_code != 200:
            raise RuntimeError(f"Create task failed HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        if data.get("code") in LIMIT_CODES:
            raise KieKeyExhausted(f"code {data.get('code')}: {data.get('msg')}")
        if data.get("code") != 200:
            raise RuntimeError(f"Create task failed: {data.get('msg')}")
        return data["data"]["taskId"]

    def _poll_task(self, task_id: str, headers: dict) -> dict:
        url = f"{self.base_url}/recordInfo?taskId={task_id}"
        start = time.time()

        with httpx.Client(timeout=30) as client:
            while time.time() - start < self.timeout:
                resp = client.get(url, headers=headers)
                if resp.status_code in LIMIT_CODES:
                    raise KieKeyExhausted(f"poll HTTP {resp.status_code}: {resp.text[:200]}")
                if resp.status_code != 200:
                    raise RuntimeError(f"Poll failed HTTP {resp.status_code}: {resp.text[:300]}")

                data = resp.json()
                if data.get("code") != 200:
                    raise RuntimeError(f"Poll failed: {data.get('msg')}")

                task = data["data"]
                state = task.get("state")

                if state == "success":
                    result_json = task.get("resultJson", "{}")
                    try:
                        result = json.loads(result_json)
                    except json.JSONDecodeError:
                        result = {"resultUrls": []}
                    result["creditsConsumed"] = task.get("creditsConsumed")
                    return result

                if state == "fail":
                    raise RuntimeError(f"Task failed: {task.get('failMsg')}")

                log.debug("kie_ai: task=%s state=%s waiting...", task_id, state)
                time.sleep(self.poll_interval)

        raise TimeoutError(f"Task {task_id} did not complete within {self.timeout}s")

    def _download_image(self, url: str) -> bytes:
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.content

    def _compress_image(self, img_bytes: bytes, max_size_mb: float) -> bytes:
        """Compress image to under max_size_mb using PIL if available."""
        try:
            from PIL import Image
            import io

            max_bytes = int(max_size_mb * 1024 * 1024)
            if len(img_bytes) <= max_bytes:
                return img_bytes

            img = Image.open(io.BytesIO(img_bytes))
            if img.mode in ("RGBA", "LA", "P"):
                bg = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                bg.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
                img = bg

            lo, hi = 10, 95
            best = img_bytes
            while lo <= hi:
                mid = (lo + hi) // 2
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=mid, optimize=True)
                data = buf.getvalue()
                if len(data) <= max_bytes:
                    best = data
                    lo = mid + 1
                else:
                    hi = mid - 1
            return best
        except Exception as e:
            log.warning("kie_ai: compression failed: %s", e)
            return img_bytes


# Convenience function for worker integration
def generate_image(
    prompt: str,
    out_path: str | Path,
    *,
    api_key: str | None = None,
    api_keys: list[str] | None = None,
    model: str = DEFAULT_MODEL,
    aspect_ratio: str = "1:1",
    output_format: str = "png",
    nsfw_checker: bool = True,
    compress: bool = True,
    max_size_mb: float = 1.0,
) -> dict:
    """One-shot generate using KieAIProvider with key pool."""
    provider = KieAIProvider(api_key=api_key, api_keys=api_keys)
    return provider.generate(
        prompt=prompt,
        out_path=out_path,
        model=model,
        aspect_ratio=aspect_ratio,
        output_format=output_format,
        nsfw_checker=nsfw_checker,
        compress=compress,
        max_size_mb=max_size_mb,
    )
