r"""Open Google Gemini using Playwright (Python) with a persistent Chrome profile.

What this is for
- Opens https://gemini.google.com/app in a real Chrome window.
- Reuses the *same* Chrome profile/session used by Copilot's Playwright MCP tools,
    so you stay logged in (no manual login each run).

Default behavior (this repo/machine)
- If available, uses: %LOCALAPPDATA%\ms-playwright\mcp-chrome-9b87fc7
    (the same user-data-dir used by MCP Playwright).

Notes
- Do not run this simultaneously with an active MCP browser session that uses the same
    profile directory, or the profile can be locked.

Examples
Default (recommended)
- Generate/download images defined in review.json, then compress (<1MB) and verify:
    python open_gemini.py

Open-only (previous default)
- Just open Gemini in a real Chrome window and keep it open until Enter:
    python open_gemini.py --open-only

- Headed smoke test (auto screenshot then exit):
    python open_gemini.py --smoke --screenshot gemini.png

- Force exactly the MCP profile:
    python open_gemini.py --use-mcp-playwright-profile

- Use a dedicated project profile (won't conflict with MCP/system):
    python open_gemini.py --user-data-dir ./.gemini-profile

- Use your system Chrome profile (likely already logged in):
    python open_gemini.py --use-system-chrome-profile --profile-directory Default

- Generate/download images defined in review.json, then compress (<1MB) and verify:
    python open_gemini.py --generate-review-images
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

DEFAULT_URL = "https://gemini.google.com/app"

# User asked to use this exact MCP Chrome profile directory.
# This is the persistent user-data-dir used by Playwright MCP on this machine.
MCP_USER_DATA_DIR_NAME = "mcp-chrome-9b87fc7"


_REPO_DIR = Path(__file__).resolve().parent
_DEFAULT_REVIEW_JSON = _REPO_DIR / "review.json"


class BrowserClosedError(RuntimeError):
    pass


def _is_target_closed_error(exc: BaseException) -> bool:
    msg = str(exc)
    return (
        "Target page, context or browser has been closed" in msg
        or "TargetClosedError" in msg
        or "has been closed" in msg
        and "Target" in msg
    )


def _extract_review_image_items(obj) -> list[dict]:
    items: list[dict] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            if (
                node.get("id") == "gambar"
                and isinstance(node.get("Path"), str)
                and isinstance(node.get("Prompt"), str)
            ):
                items.append(node)
            for v in node.values():
                walk(v)
            return

        if isinstance(node, list):
            for v in node:
                walk(v)

    walk(obj)
    return items


def _load_review_image_tasks(review_json_path: Path) -> list[dict]:
    raw = review_json_path.read_text(encoding="utf-8")
    data = json.loads(raw)
    items = _extract_review_image_items(data)

    def image_number_key(item: dict) -> tuple[int, str]:
        raw_num = item.get("ImageNumber")
        try:
            return (int(raw_num), str(raw_num))
        except Exception:
            return (10**9, str(raw_num))

    items.sort(key=image_number_key)
    return items


def _resolve_output_path(path_str: str) -> Path:
    p = Path(path_str)
    return p if p.is_absolute() else (_REPO_DIR / p)


def _ensure_gemini_image_tool_selected(page) -> None:
    # If already selected, do nothing.
    cancel = page.get_by_role(
        "button",
        name=re.compile(
            r"Batalkan pilihan\\s+Buat\\s+Gambar|Cancel selection\\s+Create image", re.IGNORECASE
        ),
    )
    try:
        cancel.wait_for(state="visible", timeout=800)
        return
    except Exception:
        pass

    # Try direct tool button (home suggestion or tool pill).
    tool_btn = page.get_by_role(
        "button",
        # On Gemini home page the accessible name often includes extra text
        # like: "🖼️ Buat Gambar, tombol, ketuk untuk menggunakan alat".
        name=re.compile(r"Buat\\s*gambar|Create\\s*image", re.IGNORECASE),
    )
    if tool_btn.count() > 0:
        tool_btn.first.click()
        try:
            cancel.wait_for(state="visible", timeout=5_000)
            return
        except Exception:
            pass

    # Try opening tools menu.
    tools_btn = page.get_by_role("button", name=re.compile(r"Alat|Tools", re.IGNORECASE))
    if tools_btn.count() > 0:
        tools_btn.first.click()
        page.wait_for_timeout(200)
        # The tool list can render as menu items or plain buttons.
        for role in ("menuitem", "button"):
            pick = page.get_by_role(
                role, name=re.compile(r"Buat\\s*Gambar|Create\\s*image", re.IGNORECASE)
            )
            if pick.count() > 0:
                pick.first.click()
                try:
                    cancel.wait_for(state="visible", timeout=5_000)
                    return
                except Exception:
                    pass

    raise RuntimeError(
        "Tidak bisa memilih tool 'Buat gambar' di Gemini (UI berubah atau tertutup dialog)"
    )


def _dismiss_obstructing_dialogs(page) -> None:
    """Best-effort close for occasional Gemini popups that block interaction."""
    # Observed in MCP: a feature-info dialog with data-test-id="close-button".
    try:
        close_btn = page.locator('[data-test-id="close-button"]')
        if close_btn.count() > 0:
            close_btn.first.click(timeout=1000)
            page.wait_for_timeout(150)
            return
    except Exception:
        pass

    # Fallbacks (language-dependent): "Lain kali" / "Not now".
    for pat in (r"Lain\\s+kali", r"Not\\s+now", r"Tutup", r"Close"):
        try:
            btn = page.get_by_role("button", name=re.compile(pat, re.IGNORECASE))
            if btn.count() > 0:
                btn.first.click(timeout=1000)
                page.wait_for_timeout(150)
                return
        except Exception:
            continue


def _find_prompt_textbox(page):
    candidates = [
        page.get_by_placeholder(re.compile(r"Minta Gemini|Ask Gemini", re.IGNORECASE)),
        page.get_by_role(
            "textbox",
            name=re.compile(
                r"Masukkan perintah|Enter a prompt|Type a prompt|Deskripsikan gambar|Describe your image",
                re.IGNORECASE,
            ),
        ),
        page.get_by_role("textbox"),
        page.locator("textarea"),
        page.locator('[contenteditable="true"]'),
    ]
    for loc in candidates:
        try:
            if loc.count() > 0:
                return loc.first
        except Exception:
            continue
    raise RuntimeError("Tidak menemukan textbox prompt di halaman Gemini")


def _ensure_pro_mode_selected(page) -> None:
    """Ensure the composer mode is set to Pro.

    MCP UI observations (Indonesian):
    - Mode button: data-test-id="bard-mode-menu-button" (also role button "Buka pemilih mode")
    - Menu contains menuitem entries including "Pro ..." and shows a check icon when active.
    """

    try:
        mode_btn = page.locator('[data-test-id="bard-mode-menu-button"]').first
        if mode_btn.count() == 0:
            mode_btn = page.get_by_role(
                "button",
                name=re.compile(r"Buka\\s+pemilih\\s+mode|Open\\s+mode\\s+picker", re.IGNORECASE),
            ).first
        if mode_btn.count() == 0:
            return

        current = (mode_btn.inner_text(timeout=1000) or "").strip()
        if re.search(r"\bPro\b", current, re.IGNORECASE):
            return

        mode_btn.click(timeout=2000)
        page.wait_for_timeout(200)

        pro_item = page.get_by_role("menuitem", name=re.compile(r"\bPro\b", re.IGNORECASE))
        if pro_item.count() > 0:
            pro_item.first.click(timeout=2000)
            page.wait_for_timeout(200)
    except Exception:
        # Best-effort; proceed if UI differs.
        return


def _send_prompt(page, prompt: str) -> None:
    box = _find_prompt_textbox(page)
    box.click()
    box.fill(prompt)
    # Prefer clicking the explicit Send button so Enter doesn't just insert a newline.
    send = page.get_by_role("button", name=re.compile(r"Kirim|Send", re.IGNORECASE))
    if send.count() > 0:
        send.last.click()
        return

    # Fallback: try Enter.
    box.press("Enter")


_DOWNLOAD_FULL_SIZE_RE = re.compile(
    # Keep this robust across Gemini UI language variants.
    # Examples observed:
    # - "Download gambar ukuran penuh"
    # - "Download full-size image"
    # - "Download image"
    r"^(Download|Unduh)\b.*\b(gambar|image)\b",
    re.IGNORECASE,
)


def _download_full_size_buttons(page):
    """Return a locator for per-response image download buttons."""
    return page.get_by_role("button", name=_DOWNLOAD_FULL_SIZE_RE)


def _wait_for_new_download_button(page, *, previous_count: int, timeout_ms: int):
    """Wait for a *new* full-size download button to appear.

    Why: Gemini keeps older "Download gambar ukuran penuh" buttons visible in the
    conversation. If we only wait for "a download button" we can click an old one
    and download the wrong image.

    Strategy: capture the count before sending the prompt, then wait until the
    count increases. The newly generated image's download button is assumed to be
    appended last.
    """

    buttons = _download_full_size_buttons(page)
    started = time.monotonic()
    deadline = started + (timeout_ms / 1000.0)

    progress_every_s = 10.0
    next_log = started + progress_every_s

    while time.monotonic() < deadline:
        try:
            count = buttons.count()
        except Exception:
            count = 0

        if count > previous_count:
            candidate = buttons.nth(previous_count)
            try:
                candidate.wait_for(state="visible", timeout=2_000)
            except Exception:
                pass
            return candidate

        now = time.monotonic()
        if now >= next_log:
            elapsed_s = int(now - started)
            total_s = max(1, int(timeout_ms / 1000.0))
            print(
                f"    ... menunggu tombol download baru: {elapsed_s}s/{total_s}s "
                f"(sebelum={previous_count}, sekarang={count})"
            )
            next_log = now + progress_every_s

        page.wait_for_timeout(500)

    raise RuntimeError("Kontrol download gambar baru tidak muncul (timeout)")


def _download_new_image(
    page, output_path: Path, *, previous_download_count: int, timeout_ms: int
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    saw_stop_button = False

    # Best-effort readiness logic:
    # - While generating, Gemini may show "Hentikan respons" (Stop response).
    # - When complete, that button disappears.
    stop_btn = page.get_by_role(
        "button",
        name=re.compile(r"Hentikan\\s+respons|Stop\\s+response|Stop\\s+generating", re.IGNORECASE),
    )

    try:
        stop_btn.wait_for(state="visible", timeout=min(10_000, timeout_ms))
    except PlaywrightTimeoutError:
        # Some UI variants don't show this button; continue with download-button waiting.
        stop_btn = None

    if stop_btn is not None:
        saw_stop_button = True
        progress_every_s = 10.0
        next_log = time.monotonic() + progress_every_s

        while True:
            now = time.monotonic()
            elapsed_ms = int((now - started) * 1000)
            remaining_ms = timeout_ms - elapsed_ms
            if remaining_ms <= 0:
                raise RuntimeError(
                    "Timeout menunggu Gemini selesai generate (tombol 'Hentikan respons' masih ada)"
                )

            try:
                stop_btn.wait_for(state="hidden", timeout=min(5_000, remaining_ms))
                break
            except PlaywrightTimeoutError:
                if now >= next_log:
                    elapsed_s = int((now - started))
                    total_s = max(1, int(timeout_ms / 1000.0))
                    print(f"    ... Gemini masih generate: {elapsed_s}s/{total_s}s")
                    next_log = now + progress_every_s
                continue

    elapsed_ms = int((time.monotonic() - started) * 1000)
    remaining_ms = max(1, timeout_ms - elapsed_ms)

    # If Gemini showed a "Stop response" button and it has disappeared, the response
    # is likely complete. If no download button appears shortly after that, it is
    # usually a text-only response (no image), so we can fail fast and let callers
    # retry with a clearer instruction.
    if saw_stop_button:
        fast_fail_ms = min(30_000, remaining_ms)
        control = _wait_for_new_download_button(
            page, previous_count=previous_download_count, timeout_ms=fast_fail_ms
        )
        elapsed_ms = int((time.monotonic() - started) * 1000)
        remaining_ms = max(1, timeout_ms - elapsed_ms)
    else:
        control = _wait_for_new_download_button(
            page, previous_count=previous_download_count, timeout_ms=remaining_ms
        )

    try:
        control.scroll_into_view_if_needed(timeout=2000)
    except Exception:
        pass
    try:
        with page.expect_download(timeout=remaining_ms) as d:
            control.click()
        d.value.save_as(str(output_path))
        return
    except Exception:
        # Fallback: sometimes the first click opens a small menu.
        try:
            control.click(timeout=2000)
            page.wait_for_timeout(200)
        except Exception:
            pass

        candidates = [
            page.get_by_role("menuitem", name=_DOWNLOAD_FULL_SIZE_RE),
            page.get_by_role("button", name=_DOWNLOAD_FULL_SIZE_RE),
            page.get_by_role("link", name=_DOWNLOAD_FULL_SIZE_RE),
            page.get_by_role("menuitem", name=re.compile(r"download|unduh", re.IGNORECASE)),
        ]

        for loc in candidates:
            try:
                item = loc.last
                if item.count() > 0:
                    with page.expect_download(timeout=remaining_ms) as d2:
                        item.click()
                    d2.value.save_as(str(output_path))
                    return
            except Exception:
                continue
        raise


def _compress_and_verify(path: Path, max_size_mb: float) -> tuple[bool, int]:
    # Import lazily so this script can still "just open" Gemini
    # even if Pillow isn't installed.
    try:
        from tools.image_generation.compress import compress_image  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "Gagal import compress.py. Pastikan dependensi terpasang (Pillow). " f"Detail: {e}"
        )

    ok = compress_image(path, max_size_mb=max_size_mb)
    size = path.stat().st_size
    # Strict "< 1MB" check (decimal) to match compress.py.
    max_bytes = int(max_size_mb * 1_000_000)
    if size >= max_bytes:
        ok = False
    return ok, size


def _default_mcp_playwright_user_data_dir() -> Path | None:
    """Playwright MCP on Windows commonly stores a persistent Chrome profile here."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None

    base = Path(local_app_data) / "ms-playwright"
    preferred = base / MCP_USER_DATA_DIR_NAME
    if preferred.exists():
        return preferred

    fallback = base / "mcp-chrome"
    return fallback if fallback.exists() else None


def _read_text(path: Path) -> str | None:
    try:
        data = path.read_bytes()
        # Chrome metadata files in user-data-dir are often UTF-16LE without BOM.
        if b"\x00" in data:
            try:
                return data.decode("utf-16-le", errors="strict").strip().strip("\x00")
            except Exception:
                pass
            try:
                return data.decode("utf-16", errors="replace").strip().strip("\x00")
            except Exception:
                pass

        return data.decode("utf-8", errors="replace").strip()
    except Exception:
        return None


def _detect_profile_directory_from_local_state(user_data_dir: Path) -> str | None:
    local_state = user_data_dir / "Local State"
    raw = _read_text(local_state)
    if not raw:
        return None

    try:
        data = json.loads(raw)
    except Exception:
        return None

    profile = data.get("profile") or {}
    last_used = profile.get("last_used")
    if isinstance(last_used, str) and last_used:
        return last_used

    # Fallbacks
    if (user_data_dir / "Default").exists():
        return "Default"
    for name in ("Profile 1", "Profile 2"):
        if (user_data_dir / name).exists():
            return name
    return None


def _detect_executable_from_last_browser(user_data_dir: Path) -> str | None:
    last_browser = user_data_dir / "Last Browser"
    exe = _read_text(last_browser)
    if not exe:
        return None
    exe_path = Path(exe)
    return str(exe_path) if exe_path.exists() else None


def _default_system_chrome_user_data_dir() -> Path | None:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None

    candidate = Path(local_app_data) / "Google" / "Chrome" / "User Data"
    return candidate if candidate.exists() else None


def _default_project_user_data_dir() -> Path:
    # Dedicated profile inside the repo (safe, no conflicts). Login will persist after first login.
    return Path(".gemini-profile")


def _is_logged_in(page) -> tuple[bool, str | None]:
    # The account button label can be Indonesian or English depending on UI.
    patterns = [r"Akun Google", r"Google Account"]
    for pat in patterns:
        locator = page.get_by_role("button", name=re.compile(pat, re.IGNORECASE))
        if locator.count() > 0:
            name = locator.first.get_attribute("aria-label") or locator.first.inner_text()
            return True, name

    # Fallback: if Gemini's composer textbox is present, we're effectively logged in.
    composer = page.get_by_role(
        "textbox",
        name=re.compile(
            r"Masukkan perintah untuk Gemini|Minta Gemini|Ask Gemini|Enter a prompt|Type a prompt|Deskripsikan gambar|Describe your image",
            re.IGNORECASE,
        ),
    )
    if composer.count() > 0:
        return True, None

    return False, None


def _wait_for_login(page, *, timeout_ms: int) -> tuple[bool, str | None, object | None]:
    """Wait until the user is logged in.

    Robustness notes:
    - Google login can redirect within the same tab, or occasionally open a new tab.
    - We therefore scan all pages in the same browser context.
    """
    started = time.monotonic()
    deadline = started + (timeout_ms / 1000.0)
    progress_every_s = 10.0
    next_log = started

    while time.monotonic() < deadline:
        pages = []
        try:
            pages = list(page.context.pages)
        except Exception:
            pages = [page]

        if not pages:
            raise RuntimeError(
                "Browser context tidak punya tab (kemungkinan window Chrome tertutup)"
            )

        for candidate in pages:
            try:
                logged_in, label = _is_logged_in(candidate)
            except PlaywrightError:
                continue

            if logged_in:
                return True, label, candidate

        now = time.monotonic()
        if now >= next_log:
            elapsed_s = int(now - started)
            total_s = max(1, int(timeout_ms / 1000.0))
            print(f"! Menunggu login Google di window Chrome: {elapsed_s}s/{total_s}s")
            next_log = now + progress_every_s

        time.sleep(1.0)

    return False, None, None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Open Gemini using Playwright with a persistent Chrome profile"
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="Target URL (default: Gemini app)")
    parser.add_argument("--headless", action="store_true", help="Run headless")
    parser.add_argument(
        "--test", action="store_true", help="Headless test + save screenshot, then exit"
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Headed smoke test: open, wait a bit, screenshot, then exit (no interaction).",
    )
    parser.add_argument(
        "--smoke-seconds",
        type=float,
        default=3.0,
        help="Seconds to wait during --smoke before taking screenshot (default: 3.0)",
    )
    parser.add_argument(
        "--screenshot",
        default="gemini_open.png",
        help="Screenshot path (used with --test). Default: gemini_open.png",
    )

    parser.add_argument(
        "--user-data-dir",
        default=None,
        help="Chrome user data dir for persistent context (overrides MCP/system/project defaults)",
    )
    parser.add_argument(
        "--use-mcp-playwright-profile",
        action="store_true",
        help=f"Use Playwright MCP profile (prefers LOCALAPPDATA\\ms-playwright\\{MCP_USER_DATA_DIR_NAME}).",
    )
    parser.add_argument(
        "--use-system-chrome-profile",
        action="store_true",
        help="Use the system Chrome User Data dir (often already logged in). Requires Chrome closed.",
    )
    parser.add_argument(
        "--profile-directory",
        default="Default",
        help='Chrome profile directory name (e.g. "Default", "Profile 1"). Default: Default',
    )
    parser.add_argument(
        "--channel",
        default="chrome",
        help='Browser channel for Chromium engine when executable path is not known (default: "chrome"). You can try "msedge" too.',
    )
    parser.add_argument(
        "--locale",
        default=None,
        help="Browser locale (e.g. en-US). If omitted and using MCP profile, defaults to en-US.",
    )
    parser.add_argument(
        "--timezone",
        default=None,
        help="Timezone id (e.g. Asia/Bangkok). If omitted and using MCP profile, defaults to Asia/Bangkok.",
    )
    parser.add_argument(
        "--viewport",
        default="1536x864",
        help="Viewport as WIDTHxHEIGHT (default: 1536x864 to match MCP run)",
    )
    parser.add_argument(
        "--print-fingerprint",
        action="store_true",
        help="Print a small browser fingerprint after opening (UA/lang/timezone/webdriver).",
    )

    parser.add_argument(
        "--open-only",
        action="store_true",
        help="Only open Gemini and wait for Enter (no automation).",
    )

    parser.add_argument(
        "--generate-review-images",
        action="store_true",
        help="Auto-generate and download all images defined in review.json (id:'gambar'), then compress (<1MB) and verify.",
    )
    parser.add_argument(
        "--review-json",
        default=str(_DEFAULT_REVIEW_JSON),
        help="Path to review.json (default: ./review.json).",
    )
    parser.add_argument(
        "--only-images",
        default=None,
        help="Optional comma-separated ImageNumber list to generate (e.g. 1,3,6). If omitted, runs all.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output files (default: skip generation if file exists, but still compress/verify).",
    )
    parser.add_argument(
        "--max-size-mb",
        type=float,
        default=1.0,
        help="Max size in MB (decimal) after compression (default: 1.0).",
    )

    args = parser.parse_args()

    # If the user runs without any explicit mode flags, default to generating all
    # images from review.json (user expectation for this repo workflow).
    if not (args.open_only or args.test or args.smoke or args.generate_review_images):
        args.generate_review_images = True

    # Derive final options.
    if args.test:
        headless = True
    elif args.smoke:
        headless = False
    elif args.generate_review_images:
        # For download + login reliability, prefer headed unless user explicitly requests headless.
        headless = args.headless
    else:
        headless = args.headless

    # Choose user-data-dir source.
    mcp_dir = _default_mcp_playwright_user_data_dir()

    if args.user_data_dir:
        user_data_dir = Path(args.user_data_dir)
        profile_directory = args.profile_directory
        executable_path = None
    elif args.use_mcp_playwright_profile or (
        mcp_dir is not None and not args.use_system_chrome_profile
    ):
        # Default to MCP profile if available (closest match to Copilot MCP browser).
        user_data_dir = mcp_dir if mcp_dir is not None else _default_project_user_data_dir()
        profile_directory = (
            _detect_profile_directory_from_local_state(user_data_dir) or args.profile_directory
        )
        executable_path = _detect_executable_from_last_browser(user_data_dir)
    elif args.use_system_chrome_profile:
        system_dir = _default_system_chrome_user_data_dir()
        if system_dir is None:
            raise SystemExit(
                "Tidak menemukan Chrome User Data di %LOCALAPPDATA%\\Google\\Chrome\\User Data"
            )
        user_data_dir = system_dir
        profile_directory = args.profile_directory
        executable_path = None
    else:
        user_data_dir = _default_project_user_data_dir()
        profile_directory = args.profile_directory
        executable_path = None

    user_data_dir.mkdir(parents=True, exist_ok=True)

    launch_args = [
        f"--profile-directory={profile_directory}",
        "--no-first-run",
        "--no-default-browser-check",
    ]

    # Defaults to match the MCP browser run we observed.
    # Note: We do NOT force Playwright's `locale` by default for MCP, because it can
    # collapse `navigator.languages` to a single value. We prefer Chrome profile + --lang.
    locale = args.locale
    timezone_id = args.timezone
    using_mcp_profile = args.use_mcp_playwright_profile or (
        mcp_dir is not None and not args.use_system_chrome_profile
    )
    if using_mcp_profile:
        timezone_id = timezone_id or "Asia/Bangkok"
        # Match MCP languages list (navigator.languages: ["en-US", "en"]).
        launch_args.append("--lang=en-US,en")
        # Attempt to match MCP's navigator.webdriver === false.
        launch_args.append("--disable-blink-features=AutomationControlled")

    m = re.match(r"^(\d+)x(\d+)$", args.viewport.strip())
    if not m:
        raise SystemExit("Format --viewport harus WIDTHxHEIGHT, contoh: 1536x864")
    viewport = {"width": int(m.group(1)), "height": int(m.group(2))}

    try:
        with sync_playwright() as p:
            print("Chrome setup:")
            print(f"- user_data_dir: {user_data_dir}")
            print(f"- profile_directory: {profile_directory}")
            if executable_path:
                print(f"- executable_path: {executable_path}")
            else:
                print(f"- channel: {args.channel}")
            print(f"- headless: {headless}")
            print(f"- viewport: {viewport['width']}x{viewport['height']}")
            if locale:
                print(f"- locale: {locale}")
            if timezone_id:
                print(f"- timezone: {timezone_id}")

            context_kwargs = dict(
                user_data_dir=str(user_data_dir),
                headless=headless,
                accept_downloads=True,
                viewport=viewport,
                args=launch_args,
            )

            if locale:
                context_kwargs["locale"] = locale
            if timezone_id:
                context_kwargs["timezone_id"] = timezone_id

            # Try to match MCP fingerprint closer by removing automation flag.
            # (MCP's browser reports navigator.webdriver === false.)
            if using_mcp_profile:
                context_kwargs["ignore_default_args"] = ["--enable-automation"]

            # If MCP profile knows the exact chrome.exe path, use it to match 1:1.
            if executable_path:
                context_kwargs["executable_path"] = executable_path
            else:
                context_kwargs["channel"] = args.channel

            context = p.chromium.launch_persistent_context(**context_kwargs)

            # Use an existing page if present; otherwise open a new one.
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(args.url, wait_until="domcontentloaded")

            # Basic readiness.
            page.wait_for_timeout(1500)

            logged_in, label = _is_logged_in(page)
            if logged_in:
                print(f"✓ Login terdeteksi: {label or 'Akun Google'}")
            else:
                print(
                    "! Login belum terdeteksi. Jika ini pertama kali, silakan login dulu di window yang terbuka."
                )

            if args.print_fingerprint:
                fp = page.evaluate(
                    """() => ({
                      ua: navigator.userAgent,
                      platform: navigator.platform,
                      webdriver: navigator.webdriver,
                      lang: navigator.language,
                      languages: navigator.languages,
                      tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
                      uaData: navigator.userAgentData ? {
                        brands: navigator.userAgentData.brands,
                        mobile: navigator.userAgentData.mobile,
                        platform: navigator.userAgentData.platform,
                      } : null,
                    })"""
                )
                print("Fingerprint:")
                print(json.dumps(fp, ensure_ascii=False, indent=2))

            if args.generate_review_images:
                if not logged_in:
                    try:
                        ok_login, label2, login_page = _wait_for_login(page, timeout_ms=600_000)
                    except Exception as e:
                        print(f"✗ Gagal menunggu login: {e}")
                        context.close()
                        return 4
                    if ok_login:
                        logged_in = True
                        if login_page is not None:
                            page = login_page
                            try:
                                if "gemini.google.com" not in (page.url or ""):
                                    page.goto(args.url, wait_until="domcontentloaded")
                                    page.wait_for_timeout(1500)
                            except Exception:
                                pass
                        print(f"✓ Login terdeteksi: {label2 or 'Akun Google'}")
                    else:
                        print(
                            "✗ Login tidak terdeteksi (timeout). Jalankan ulang setelah login selesai."
                        )
                        context.close()
                        return 4

                review_json_path = Path(args.review_json)
                if not review_json_path.is_absolute():
                    review_json_path = (_REPO_DIR / review_json_path).resolve()
                if not review_json_path.exists():
                    raise RuntimeError(f"review.json tidak ditemukan: {review_json_path}")

                only_set: set[str] | None = None
                if args.only_images:
                    only_set = {s.strip() for s in args.only_images.split(",") if s.strip()}

                tasks = _load_review_image_tasks(review_json_path)
                if only_set is not None:
                    tasks = [t for t in tasks if str(t.get("ImageNumber")) in only_set]

                if not tasks:
                    raise RuntimeError("Tidak ada entry gambar yang cocok di review.json")

                print(f"\nReview images: {len(tasks)} task(s)")

                # Best-effort: ensure image tool selected once.
                _ensure_gemini_image_tool_selected(page)

                ok_count = 0
                fail_count = 0

                max_browser_restarts = 3
                browser_restarts_used = 0

                task_index = 0
                while task_index < len(tasks):
                    item = tasks[task_index]
                    image_number = str(item.get("ImageNumber") or "")
                    title = str(item.get("Title") or "")
                    prompt = str(item.get("Prompt") or "")
                    out_path_str = str(item.get("Path") or "")
                    out_path = _resolve_output_path(out_path_str)

                    print("\n" + ("-" * 70))
                    header = f"Image {image_number}" if image_number else "Image"
                    if title:
                        header += f": {title}"
                    print(header)
                    print(f"- Path: {out_path}")

                    try:
                        try:
                            if out_path.exists() and not args.overwrite:
                                print("  • File sudah ada → skip generate (compress+verify saja)")
                            else:
                                max_attempts = 3
                                last_err: Exception | None = None

                                for attempt in range(1, max_attempts + 1):
                                    print(f"  • Attempt {attempt}/{max_attempts}")
                                    _dismiss_obstructing_dialogs(page)
                                    _ensure_gemini_image_tool_selected(page)
                                    _ensure_pro_mode_selected(page)

                                    attempt_prompt = prompt
                                    if attempt > 1:
                                        attempt_prompt = f"{prompt}\n\n+ tolong buatkan gambar"

                                    try:
                                        prev_download_count = _download_full_size_buttons(
                                            page
                                        ).count()
                                    except Exception as e:
                                        if _is_target_closed_error(e):
                                            raise BrowserClosedError(str(e)) from e
                                        prev_download_count = 0

                                    _send_prompt(page, attempt_prompt)

                                    try:
                                        _download_new_image(
                                            page,
                                            out_path,
                                            previous_download_count=prev_download_count,
                                            timeout_ms=180_000,
                                        )
                                        last_err = None
                                        print("  ✓ Download selesai")
                                        break
                                    except Exception as e:
                                        if _is_target_closed_error(e):
                                            raise BrowserClosedError(str(e)) from e
                                        last_err = e
                                        if attempt < max_attempts:
                                            print(
                                                "  ! Tidak ada gambar (atau salah format). "
                                                "Retry dengan '+ tolong buatkan gambar'. "
                                                f"Detail: {e}"
                                            )
                                            continue
                                        raise

                                if last_err is not None:
                                    raise last_err

                            ok, size = _compress_and_verify(out_path, max_size_mb=args.max_size_mb)
                            if ok:
                                ok_count += 1
                                print(f"  ✓ Verified < {args.max_size_mb}MB (bytes: {size})")
                            else:
                                fail_count += 1
                                print(f"  ✗ Ukuran masih >= {args.max_size_mb}MB (bytes: {size})")

                            task_index += 1
                            continue
                        except Exception as e:
                            if isinstance(e, BrowserClosedError):
                                raise
                            if _is_target_closed_error(e):
                                raise BrowserClosedError(str(e)) from e
                            raise

                    except BrowserClosedError as e:
                        if browser_restarts_used >= max_browser_restarts:
                            fail_count += 1
                            print(f"  ✗ Browser/tab tertutup berulang kali → skip. Detail: {e}")
                            task_index += 1
                            continue

                        browser_restarts_used += 1
                        print(
                            f"  ! Browser/tab tertutup. Restart browser ({browser_restarts_used}/{max_browser_restarts}) "
                            "lalu retry image ini..."
                        )

                        try:
                            context.close()
                        except Exception:
                            pass

                        context = p.chromium.launch_persistent_context(**context_kwargs)
                        page = context.pages[0] if context.pages else context.new_page()
                        page.goto(args.url, wait_until="domcontentloaded")
                        page.wait_for_timeout(1500)

                        logged_in, label = _is_logged_in(page)
                        if logged_in:
                            print(f"✓ Login terdeteksi: {label or 'Akun Google'}")
                        else:
                            try:
                                ok_login, label2, login_page = _wait_for_login(
                                    page, timeout_ms=600_000
                                )
                                if not ok_login:
                                    raise RuntimeError("Login tidak terdeteksi (timeout)")
                                logged_in = True
                                if login_page is not None:
                                    page = login_page
                                try:
                                    if "gemini.google.com" not in (page.url or ""):
                                        page.goto(args.url, wait_until="domcontentloaded")
                                        page.wait_for_timeout(1500)
                                except Exception:
                                    pass
                                print(f"✓ Login terdeteksi: {label2 or 'Akun Google'}")
                            except Exception as e2:
                                print(f"  ✗ Gagal restart karena login: {e2}")
                                context.close()
                                return 4

                        _ensure_gemini_image_tool_selected(page)
                        continue

                    except Exception as e:
                        fail_count += 1
                        try:
                            snap = _REPO_DIR / f"gemini_failed_image_{image_number or 'x'}.png"
                            page.screenshot(path=str(snap), full_page=True)
                            print(f"  ✗ Gagal generate/download: {e}")
                            print(f"  • Screenshot debug: {snap}")
                        except Exception:
                            print(f"  ✗ Gagal generate/download: {e}")
                        task_index += 1
                        continue

                print("\n" + ("=" * 70))
                print(f"Done. OK: {ok_count}, FAIL: {fail_count}")
                print(("=" * 70))

                context.close()
                return 0 if fail_count == 0 else 3

            if args.test:
                screenshot_path = Path(args.screenshot)
                page.screenshot(path=str(screenshot_path), full_page=True)
                print(f"✓ Screenshot tersimpan: {screenshot_path}")
                context.close()
                return 0

            if args.smoke:
                page.wait_for_timeout(int(args.smoke_seconds * 1000))
                screenshot_path = Path(args.screenshot)
                page.screenshot(path=str(screenshot_path), full_page=True)
                print(f"✓ Screenshot tersimpan: {screenshot_path}")
                context.close()
                return 0

            if not headless:
                input("Browser sudah terbuka. Tekan Enter untuk menutup... ")

            context.close()
            return 0

    except PlaywrightError as e:
        msg = str(e)
        print("✗ Playwright error:")
        print(msg)

        if "Opening in existing browser session" in msg:
            print(
                "\nPenyebab paling umum: Chrome masih terbuka dan sedang memakai profile (user-data-dir) yang sama. "
                "Chrome akan menolak dibuka 2x dengan profile yang sama, sehingga proses baru langsung exit "
                "dan Playwright melihatnya sebagai TargetClosedError.\n"
                "Solusi: tutup semua window Chrome yang memakai profile ini (termasuk jika ada terminal open_gemini.py "
                "yang masih menunggu Enter), lalu jalankan lagi.\n"
            )

        if args.use_system_chrome_profile:
            print(
                "\nTip: Tutup semua Chrome/Edge yang sedang berjalan, lalu coba lagi. "
                "System profile biasanya terkunci jika Chrome masih terbuka."
            )
        if args.use_mcp_playwright_profile:
            print(
                "\nTip: Jika error menyebut profile terkunci, pastikan tidak ada sesi MCP/Playwright lain "
                "yang sedang memakai profile `mcp-chrome` saat Anda menjalankan script ini."
            )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
