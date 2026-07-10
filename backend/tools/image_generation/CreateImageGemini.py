"""Generate gambar via Gemini menggunakan profile Playwright + cookies hasil
GeminiCookies.py, dengan round-robin 4 akun.

Cara kerja
- Tiap akun punya persistent Chrome profile sendiri di
  imageGenerator/account{1..4}/. Kita launch Chrome (channel=chrome) dengan
  profile itu — sudah login otomatis.
- Untuk lingkungan tanpa display (server/headless), bungkus eksekusi dengan
  `xvfb-run -a python CreateImageGemini.py …`. Skrip tetap "headed" di mata
  Chrome (Gemini render normal), tapi user tidak melihat window apa pun.
- Image bytes diambil via response intercept: kita listen response dari
  endpoint `…/rd-gg-dl/…` yang content-type-nya `image/*` lalu simpan langsung.
- Image hasil dipipe ke compress_image() supaya ukurannya < 1MB.

CLI
    # 1 prompt -> 1 file
    xvfb-run -a python CreateImageGemini.py --prompt "kucing astronot" --out kucing.jpg

    # banyak prompt round-robin
    xvfb-run -a python CreateImageGemini.py --prompts-json prompts.json --out-dir image/

    # cek pool akun
    xvfb-run -a python CreateImageGemini.py --check

Format prompts.json (list):
    [
      {"name": "01.png", "prompt": "..."},
      {"name": "02.png", "prompt": "..."}
    ]

Library
    from tools.image_generation.CreateImageGemini import GeminiPool

    with GeminiPool.from_env() as pool:
        pool.generate_image("a futuristic city", "out.png")
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import queue
import re
import threading
import time
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass

try:
    from tools.image_generation.compress import compress_image
except Exception:
    compress_image = None  # type: ignore


REPO_DIR = Path(__file__).resolve().parent
RR_STATE_PATH = REPO_DIR / ".rr-state.json"
GEMINI_URL = "https://gemini.google.com/app"
DEFAULT_VIEWPORT = (1536, 864)
DOWNLOAD_BTN_RE = re.compile(r"^(Download|Unduh)\b.*\b(gambar|image)\b", re.IGNORECASE)

# Module-level logger for CLI output
log = logging.getLogger(__name__)

# ── Per-account logging ────────────────────────────────────────────────
# Each Gemini account gets its own log file under logs/generator/<name>.log so
# we can audit round-robin and isolate failures per slot. The directory is
# created lazily on first launch().
LOG_DIR_ENV = os.environ.get("GEMINI_LOG_DIR")
if LOG_DIR_ENV:
    _env_log_dir = Path(LOG_DIR_ENV)
    LOG_DIR = _env_log_dir if _env_log_dir.is_absolute() else REPO_DIR.parent.parent / "log" / _env_log_dir.name
else:
    # Use backend/log/ for all generation logs
    LOG_DIR = REPO_DIR.parent.parent / "log"

_LOGGERS: dict[str, logging.Logger] = {}
_LOGGERS: dict[str, logging.Logger] = {}
_LOGGERS_LOCK = threading.Lock()

def _get_account_logger(name: str) -> logging.Logger:
    with _LOGGERS_LOCK:
        if name in _LOGGERS:
            return _LOGGERS[name]
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger(f"gemini.{name}")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        from utils.core.hourly_log_handler import HourlyFileHandler
        fh = HourlyFileHandler(str(LOG_DIR), f"{name}.log", level=logging.INFO)
        logger.addHandler(fh)
        _LOGGERS[name] = logger
        return logger


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


# ─────────────────────────────────────────────────────────────── helpers


def _looks_like_image(data: bytes | None) -> bool:
    if not data or len(data) < 32:
        return False
    head = data[:8]
    return (
        head.startswith(b"\xff\xd8\xff")  # JPEG
        or head.startswith(b"\x89PNG\r\n\x1a\n")  # PNG
        or head.startswith(b"GIF8")  # GIF
        or head.startswith(b"RIFF")  # WEBP container
    )


def _cleanup_singleton(profile_dir: Path) -> None:
    """Hapus stale Chrome SingletonLock yang bisa bikin launch gagal."""
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        for p in (profile_dir / name, profile_dir / "Default" / name):
            with suppress(Exception):
                if p.exists() or p.is_symlink():
                    p.unlink()


def _click_via_js(page, aria_labels: list[str]) -> bool:
    """Klik tombol berdasarkan aria-label (pertama yang ketemu, tidak disabled)."""
    sel = ", ".join(f'button[aria-label="{a}"]' for a in aria_labels)
    return bool(
        page.evaluate(
            """(sel) => {
                const b = [...document.querySelectorAll(sel)].find(x => !x.disabled);
                if (b) { b.click(); return true; }
                return false;
            }""",
            sel,
        )
    )


def _debug_dump_menu_items(page) -> str:
    """Dump all visible menu/button items to help diagnose UI drift."""
    try:
        return page.evaluate(
            """() => {
                const items = [...document.querySelectorAll(
                    '[role="menuitemcheckbox"],[role="menuitemradio"],[role="menuitem"],' +
                    'button.mat-mdc-menu-item,.mat-mdc-menu-item,' +
                    'button[aria-label]'
                )];
                const visible = items
                    .filter(el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length))
                    .map(el => JSON.stringify({
                        tag: el.tagName,
                        role: el.getAttribute('role'),
                        aria: (el.getAttribute('aria-label') || '').slice(0, 60),
                        text: (el.textContent || '').trim().slice(0, 60),
                        class: (el.className || '').slice(0, 40)
                    }))
                    .slice(0, 30);
                return visible.join('|');
            }"""
        )
    except Exception:
        return "(dump failed)"


def _open_image_tool(page, *, timeout_s: int = 30) -> None:
    """Aktifkan mode \"Buat gambar\" via menu 'Upload & alat'.

    UI Gemini (per Jun 2026): tombol composer 'Upload & alat' membuka menu
    berisi item menuitemcheckbox: 'Buat gambar', 'Buat video', 'Buat musik',
    'Canvas', plus 'Upload file' / 'Tambahkan dari Drive'. Kita HARUS lewat
    menu ini — JANGAN klik tombol aria-label*=\"Create image\"/\"Buat Gambar\"
    langsung karena itu false-match ke item RIWAYAT percakapan di sidebar
    (judul chat lama yang kebetulan memuat teks 'create image ...').
    
    IMPROVED (Jul 2026): broader selector matching, multiple fallback
    strategies, detailed debug logging on failure.
    """
    deadline = time.monotonic() + timeout_s

    # Dismiss any blocking overlay first (e.g. "Memulai" dialog).
    _dismiss_gemini_overlays(page)

    # Step 1: open the visible "Upload & alat" / "Upload & tools" button.
    # Try multiple selector strategies in order.
    opened = False
    strategies = [
        # Strategy A: exact aria-label match (ID/EN)
        """() => {
            const btns = [...document.querySelectorAll('button[aria-label]')];
            const b = btns.find(x => {
                const a = (x.getAttribute('aria-label') || '').trim();
                const vis = !!(x.offsetWidth || x.offsetHeight || x.getClientRects().length);
                return vis && /^(Upload\\s*&\\s*(alat|tools))$/i.test(a);
            });
            if (b) { b.click(); return true; }
            return false;
        }""",
        # Strategy B: contains "Upload" in aria-label (broader match)
        """() => {
            const btns = [...document.querySelectorAll('button[aria-label]')];
            const b = btns.find(x => {
                const a = (x.getAttribute('aria-label') || '').toLowerCase().trim();
                const vis = !!(x.offsetWidth || x.offsetHeight || x.getClientRects().length);
                return vis && a.includes('upload') && !a.includes('file');
            });
            if (b) { b.click(); return true; }
            return false;
        }""",
        # Strategy C: find by text content in the composer area
        """() => {
            const composer = document.querySelector('.composer-area, .input-area, [class*="composer"], [class*="input-row"], rich-textarea');
            if (!composer) return false;
            const btns = composer.querySelectorAll('button');
            const b = [...btns].find(x => {
                const t = (x.textContent || '').toLowerCase().trim();
                const vis = !!(x.offsetWidth || x.offsetHeight || x.getClientRects().length);
                return vis && (t.includes('upload') || t.includes('alat'));
            });
            if (b) { b.click(); return true; }
            return false;
        }""",
    ]
    
    for i, strategy_js in enumerate(strategies):
        if opened:
            break
        while time.monotonic() < deadline and not opened:
            try:
                opened = bool(page.evaluate(strategy_js))
            except Exception:
                pass
            if not opened:
                page.wait_for_timeout(500)
    
    if not opened:
        debug_info = _debug_dump_menu_items(page)
        raise RuntimeError(
            f"Tidak bisa membuka menu 'Upload & alat' dalam {timeout_s}s. "
            f"Kemungkinan: UI Gemini berubah, network lambat, atau page belum load. "
            f"Visible items: {debug_info[:300]}"
        )
    page.wait_for_timeout(1000)

    # Step 2: click the "Buat gambar" / "Create image" menu item.
    # Try multiple selector strategies.
    selected = None
    menu_strategies = [
        # Strategy A: menuitemcheckbox with image-related text (but NOT video/music)
        """() => {
            const items = [...document.querySelectorAll(
                '[role="menuitemcheckbox"],[role="menuitemradio"],[role="menuitem"],' +
                'button.mat-mdc-menu-item,.mat-mdc-menu-item,' +
                '.cdk-overlay-pane button,.cdk-overlay-pane [role="menuitem"]'
            )];
            for (const el of items) {
                const vis = !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                if (!vis) continue;
                const t = ((el.getAttribute('aria-label') || '') + ' ' + (el.textContent || ''))
                    .toLowerCase().trim();
                const wantsImage = t.includes('buat gambar') || t.includes('create image')
                    || (t.includes('gambar') && !t.includes('video'));
                const isOther = t.includes('video') || t.includes('musik') || t.includes('music')
                    || t.includes('canvas') || t.includes('upload') || t.includes('drive');
                if (wantsImage && !isOther) {
                    el.click();
                    return (el.textContent || '').trim().slice(0, 40) || 'ok';
                }
            }
            return null;
        }""",
        # Strategy B: any visible menu/button with "gambar" in text
        """() => {
            const all = [...document.querySelectorAll(
                'button, [role="menuitemcheckbox"], [role="menuitemradio"], [role="menuitem"],' +
                '.cdk-overlay-pane *[role]'
            )];
            for (const el of all) {
                const vis = !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                if (!vis) continue;
                const t = (el.textContent || '').toLowerCase().trim();
                if (t === 'buat gambar' || t === 'create image' || t === 'image') {
                    el.click();
                    return t.slice(0, 40);
                }
            }
            return null;
        }""",
        # Strategy C: keyboard navigation fallback (Tab then Enter)
        """() => {
            // If image mode already active, the composer placeholder may indicate it
            const placeholders = [...document.querySelectorAll('[placeholder], [class*="placeholder"]')];
            for (const el of placeholders) {
                const t = (el.getAttribute('placeholder') || el.textContent || '').toLowerCase();
                if (t.includes('gambar') || t.includes('image')) {
                    return 'placeholder_match';
                }
            }
            return null;
        }""",
    ]
    
    for i, strategy_js in enumerate(menu_strategies):
        try:
            result = page.evaluate(strategy_js)
            if result:
                selected = result
                break
        except Exception:
            pass
    
    # Strategy C alternative: if placeholder says "describe image", image mode may already be active
    if selected == "placeholder_match":
        log.info("Image mode appears already active (composer placeholder matched)")
        selected = "already_active"
    elif not selected:
        debug_items = _debug_dump_menu_items(page)
        raise RuntimeError(
            "Tidak menemukan menu item 'Buat gambar' di Upload & alat. "
            f"Kemungkinan: UI Gemini berubah atau menu tidak muncul. "
            f"Visible menu items: {debug_items[:400]}"
        )
    
    page.wait_for_timeout(1500)


def _dismiss_gemini_overlays(page) -> None:
    """Dismiss any cdk-overlay dialogs (e.g. 'Memulai' / Getting Started) that block the composer."""
    try:
        page.evaluate(
            """() => {
                // Close all cdk-overlay backdrops and panes (Angular Material dialogs, snackbars, etc.)
                document.querySelectorAll('.cdk-overlay-backdrop, .cdk-overlay-container .cdk-overlay-backdrop-showing').forEach(el => {
                    try { el.click(); } catch(e) {}
                });
                // Also try pressing Escape to dismiss any open overlay
                document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
                // Remove overlay panes directly
                document.querySelectorAll('.cdk-overlay-pane, .mat-mdc-dialog-container, .mat-dialog-container').forEach(el => {
                    try { el.remove(); } catch(e) {}
                });
            }"""
        )
        page.wait_for_timeout(500)
    except Exception:
        pass


def _send_prompt(page, prompt: str, *, timeout_s: int = 30) -> None:
    try:
        box = page.locator('div[contenteditable="true"]').first
        # Dismiss overlays (e.g. "Memulai" dialog) that may intercept clicks
        _dismiss_gemini_overlays(page)
        try:
            box.click(timeout=timeout_s * 1000)
        except PlaywrightTimeoutError:
            # Retry after another overlay dismiss + force click via JS
            _dismiss_gemini_overlays(page)
            page.evaluate('(el) => el.click()', box.element_handle())
        # Clear any residual text in the composer.
        with suppress(Exception):
            page.keyboard.press("Control+A")
            page.keyboard.press("Delete")
        # CRITICAL: type via REAL keystrokes, not box.fill(). fill() sets the
        # contenteditable text but does NOT fire the input/beforeinput events
        # Gemini's Angular composer needs to enable the "Kirim pesan" (Send)
        # button — leaving Send disabled so the prompt is never submitted.
        page.keyboard.type(prompt, delay=2)
        page.wait_for_timeout(600)
        # Wait until the EXACT "Kirim pesan"/"Send message" button is present
        # and enabled, then click it. _click_via_js matches aria-label exactly
        # (button[aria-label="Kirim pesan"]), so it won't false-match sidebar
        # history items whose titles merely contain the word "kirim"/"send".
        deadline = time.monotonic() + 15
        sent = False
        while time.monotonic() < deadline:
            if _click_via_js(page, ["Kirim pesan", "Send message"]):
                sent = True
                break
            page.wait_for_timeout(500)
        if not sent:
            # Fallback: Enter key submits in most composer states.
            box.press("Enter")
    except PlaywrightTimeoutError:
        raise RuntimeError(
            f"Timeout {timeout_s}s saat mengirim prompt. "
            "Composer box tidak ditemukan atau tidak bisa diklik."
        )


def _wait_download_button(page, *, timeout_s: int) -> object:
    deadline = time.monotonic() + timeout_s
    next_log = time.monotonic() + 15
    log = logging.getLogger("gemini.wait")
    while time.monotonic() < deadline:
        cnt = page.locator(
            'button[aria-label="Download gambar ukuran penuh"], '
            'button[aria-label*="Download full-size image"]'
        ).count()
        if cnt > 0:
            return page.locator(
                'button[aria-label="Download gambar ukuran penuh"], '
                'button[aria-label*="Download full-size image"]'
            ).last
        if time.monotonic() >= next_log:
            elapsed = int(time.monotonic() - (deadline - timeout_s))
            log.debug("waiting for image download button (elapsed %ds/%ds)", elapsed, timeout_s)
            next_log = time.monotonic() + 15
        page.wait_for_timeout(2500)
    raise RuntimeError("Tombol download tidak muncul dalam batas waktu")


# ─────────────────────────────────────────────────────────────── pool


@dataclass
class GeminiAccount:
    name: str
    user_data_dir: Path
    email: str | None = None

    context: object | None = field(default=None, repr=False)
    page: object | None = field(default=None, repr=False)
    img_q: queue.Queue = field(default_factory=queue.Queue, repr=False)
    redirect_q: queue.Queue = field(default_factory=queue.Queue, repr=False)
    requests_made: int = 0
    # Health tracking
    success_count: int = 0
    fail_count: int = 0
    last_request_time: float = 0.0
    cooldown_until: float = 0.0  # timestamp when account can be used again

    @classmethod
    def from_env(cls, slot_name: str) -> "GeminiAccount":
        m = re.search(r"(\d+)$", slot_name)
        if not m:
            raise ValueError(f"Slot harus berakhir digit: {slot_name!r}")
        n = m.group(1)
        profiles_dir = Path(os.environ.get("GEMINI_PROFILES_DIR", REPO_DIR))
        user_data_dir = profiles_dir / slot_name
        if not user_data_dir.exists():
            raise FileNotFoundError(
                f"Profile {slot_name} tidak ada: {user_data_dir}. "
                "Jalankan GeminiCookies.py --slot {N} dulu."
            )
        email = os.environ.get(f"GEMINI_ACCOUNT{n}_EMAIL")
        return cls(name=slot_name, user_data_dir=user_data_dir, email=email)

    def launch(self, p) -> None:
        if self.context is not None:
            return
        _cleanup_singleton(self.user_data_dir)
        # Default headless=True for server/CI use; set GEMINI_HEADLESS=0 only
        # if you need to debug visually. Persistent profile keeps Chrome
        # logged in across runs, so headless launch works fine.
        headless = _env_bool("GEMINI_HEADLESS", True)
        log = _get_account_logger(self.name)
        log.info("launching browser (headless=%s, profile=%s)", headless, self.user_data_dir)
        launch_args = [
            "--profile-directory=Default",
            "--no-first-run",
            "--no-default-browser-check",
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--lang=en-US,en",
        ]
        if headless:
            # New headless mode renders a real Chromium pipeline; the legacy
            # one breaks Gemini's WebGL/canvas detection.
            launch_args.append("--headless=new")
            launch_args.append("--disable-gpu")
        self.context = p.chromium.launch_persistent_context(
            user_data_dir=str(self.user_data_dir),
            channel="chrome",
            headless=headless,
            accept_downloads=True,
            viewport={"width": DEFAULT_VIEWPORT[0], "height": DEFAULT_VIEWPORT[1]},
            args=launch_args,
            ignore_default_args=["--enable-automation"],
            timezone_id="Asia/Bangkok",
        )
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.on("response", self._on_response)
        self.page.goto(GEMINI_URL, wait_until="domcontentloaded")
        self.page.wait_for_timeout(4000)
        # CHECK: detect if cookies are expired (redirect to login page)
        self._check_login_state(log)
        log.info("browser ready")

    def _check_login_state(self, log) -> bool:
        """Detect if we landed on the login page instead of Gemini.
        Returns True if logged in, raises if cookies expired.
        """
        try:
            url = self.page.url or ""
            # Login redirects: accounts.google.com, login.live.com, etc.
            login_indicators = [
                "accounts.google.com",
                "/signin",
                "/login",
                "ServiceLogin",
                "AccountChooser",
            ]
            if any(ind in url for ind in login_indicators):
                self.close()
                raise RuntimeError(
                    f"{self.name}: Cookies expired! Redirected to: {url[:100]}. "
                    f"Re-run GeminiCookies.py --slot {self.name} to re-login."
                )
            # Double-check: Gemini page should have the composer or chat interface
            has_composer = self.page.evaluate(
                """() => {
                    return !!(
                        document.querySelector('[contenteditable="true"]') ||
                        document.querySelector('.composer-area, [class*="composer"]') ||
                        document.querySelector('rich-textarea') ||
                        document.querySelector('[aria-label*="Kirim" i], [aria-label*="Send" i]')
                    );
                }"""
            )
            if not has_composer:
                log.warning(
                    "%s: No composer detected after navigation (url=%s). "
                    "Cookies may be expired or page load incomplete.",
                    self.name, url[:80]
                )
            return True
        except RuntimeError:
            raise
        except Exception as e:
            log.warning("%s: login check error: %s", self.name, e)
            return True  # Don't block on check errors

    def _on_response(self, resp) -> None:
        try:
            url = resp.url
            # Early filter: only process Gemini download URLs
            if "/rd-gg-dl/" not in url and "/gg-dl/" not in url:
                return
            ct = resp.headers.get("content-type", "")
            if "/rd-gg-dl/" in url and ct.startswith("image/"):
                with suppress(Exception):
                    self.img_q.put(resp.body())
            elif (
                "/gg-dl/" in url
                and "alr=yes" in url
                and "rd-gg-dl" not in url
                and ct.startswith("text/plain")
            ):
                with suppress(Exception):
                    txt = resp.text().strip()
                    if txt.startswith("http"):
                        self.redirect_q.put(txt)
        except Exception:
            pass

    def close(self) -> None:
        if self.context is not None:
            with suppress(Exception):
                self.context.close()
            self.context = None
            self.page = None

    def _drain_queues(self) -> None:
        for q in (self.img_q, self.redirect_q):
            while not q.empty():
                with suppress(Exception):
                    q.get_nowait()

    def _reset_chat(self) -> None:
        """Mulai percakapan BARU yang benar-benar kosong.

        Penting: menu 'Buat gambar' HANYA muncul di chat kosong. Begitu chat
        punya pesan (atau profile persistent membuka chat lama saat launch),
        menu menyusut jadi Upload/Drive/Canvas dan image-mode tak bisa diaktifkan.
        page.goto('/app') sering me-restore chat terakhir, jadi kita klik tombol
        'Percakapan baru' secara eksplisit; goto dipakai sebagai fallback.
        """
        if self.page is None:
            return
        page = self.page
        clicked = False
        with suppress(Exception):
            clicked = bool(
                page.evaluate(
                    """() => {
                        const cands = [...document.querySelectorAll('a[aria-label], button[aria-label]')];
                        const b = cands.find(x => {
                            const a = (x.getAttribute('aria-label') || '').toLowerCase().trim();
                            const vis = !!(x.offsetWidth || x.offsetHeight || x.getClientRects().length);
                            return vis && (
                                a === 'percakapan baru' || a === 'obrolan baru' ||
                                a === 'new chat' || a === 'chat baru'
                            );
                        });
                        if (b) { b.click(); return true; }
                        return false;
                    }"""
                )
            )
        if clicked:
            page.wait_for_timeout(2000)
        else:
            with suppress(Exception):
                page.goto(GEMINI_URL, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)

    def generate_image(self, prompt: str, out_path: Path, *, generate_timeout_s: int = 240) -> dict:
        """Generate satu gambar lalu simpan ke out_path. Tidak return sampai file ada di disk."""
        if self.page is None:
            raise RuntimeError(f"{self.name}: launch() belum dipanggil")
        page = self.page
        log = _get_account_logger(self.name)
        t0 = time.time()
        log.info("job start: out=%s prompt_len=%d", out_path, len(prompt or ""))

        # Selalu mulai chat baru: menu 'Buat gambar' hanya ada di chat kosong,
        # dan profile persistent sering me-restore chat lama saat launch.
        self._reset_chat()

        self._drain_queues()
        _open_image_tool(page)
        _send_prompt(page, prompt)

        btn = _wait_download_button(page, timeout_s=generate_timeout_s)
        with suppress(Exception):
            btn.scroll_into_view_if_needed()
        page.wait_for_timeout(500)

        # Race: expect_download (file dari Chrome) vs response intercept.
        img_bytes: bytes | None = None
        download_path: Path | None = None
        try:
            with page.expect_download(timeout=15_000) as dl_event:
                btn.click()
            with suppress(Exception):
                tmp = dl_event.value.path()
                if tmp and Path(tmp).exists():
                    download_path = Path(tmp)
        except PlaywrightTimeoutError:
            # Klik tetap terjadi; Chrome mungkin treat sebagai navigation, response intercept akan tangkap.
            pass

        if download_path is not None:
            img_bytes = download_path.read_bytes()

        # Tunggu image bytes / redirect URL (dari intercept).
        # Timeout harus lebih lama dari generate_timeout_s karena download button
        # bisa muncul di detik terakhir, lalu butuh waktu extra untuk intercept.
        intercept_timeout = generate_timeout_s + 30
        if img_bytes is None or not _looks_like_image(img_bytes):
            deadline = time.time() + intercept_timeout
            collected_redirect: str | None = None
            while time.time() < deadline and (
                img_bytes is None or not _looks_like_image(img_bytes)
            ):
                try:
                    candidate = self.img_q.get(timeout=1)
                    if _looks_like_image(candidate):
                        img_bytes = candidate
                        break
                except queue.Empty:
                    pass
                try:
                    collected_redirect = self.redirect_q.get_nowait()
                except queue.Empty:
                    pass

            if (img_bytes is None or not _looks_like_image(img_bytes)) and collected_redirect:
                # follow redirect 1-2 kali sampai dapat bytes image
                cur = collected_redirect
                for _ in range(3):
                    r = self.context.request.get(
                        cur, headers={"Referer": "https://gemini.google.com/"}
                    )
                    body = r.body()
                    if _looks_like_image(body):
                        img_bytes = body
                        break
                    txt = body.decode("utf-8", errors="ignore").strip()
                    if txt.startswith("http"):
                        cur = txt
                        continue
                    break

        if img_bytes is None or not _looks_like_image(img_bytes):
            raise RuntimeError(
                f"Gagal capture image bytes setelah {intercept_timeout}s. "
                f"Download button muncul tapi image tidak ter-intercept. "
                f"Kemungkinan: network issue, Gemini API berubah, atau rate limit."
            )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(img_bytes)
        self.requests_made += 1
        elapsed = time.time() - t0
        log.info(
            "job done: out=%s size=%d bytes in %.1fs (req#%d)",
            out_path,
            len(img_bytes),
            elapsed,
            self.requests_made,
        )
        return {
            "path": str(out_path),
            "account": self.name,
            "email": self.email,
            "size": len(img_bytes),
        }


@dataclass
class GeminiPool:
    accounts: list[GeminiAccount]
    state_path: Path = RR_STATE_PATH
    cooldown_s: float = 8.0  # minimum delay between requests per account (increased from 4.0)
    max_consecutive_fails: int = 3  # after N fails, put account in extended cooldown
    extended_cooldown_s: float = 60.0  # extended cooldown after too many fails

    _pw_cm: object | None = field(default=None, repr=False)
    _pw: object | None = field(default=None, repr=False)

    @classmethod
    def from_env(cls) -> "GeminiPool":
        names_env = os.environ.get("GEMINI_PROFILES", "account1,account2,account3,account4")
        names = [n.strip() for n in names_env.split(",") if n.strip()]
        accounts: list[GeminiAccount] = []
        log = logging.getLogger("gemini.pool")
        for n in names:
            try:
                accounts.append(GeminiAccount.from_env(n))
            except Exception as e:
                log.warning("skip account %s: %s", n, e)
        if not accounts:
            raise RuntimeError("Tidak ada akun valid. Jalankan GeminiCookies.py.")
        pool = cls(accounts=accounts)
        pool._pw_cm = sync_playwright()
        pool._pw = pool._pw_cm.__enter__()
        return pool

    def __enter__(self) -> "GeminiPool":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        # Close all accounts even if some fail
        for a in self.accounts:
            with suppress(Exception):
                a.close()
        if self._pw_cm is not None:
            with suppress(Exception):
                self._pw_cm.__exit__(None, None, None)
            self._pw_cm = None
            self._pw = None

    def _next_index(self) -> int:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            idx = int(data.get("next", 0))
        except Exception:
            idx = 0
        idx %= len(self.accounts)
        nxt = (idx + 1) % len(self.accounts)
        with suppress(Exception):
            self.state_path.write_text(
                json.dumps({"next": nxt, "updated_at": time.time()}), encoding="utf-8"
            )
        chosen = self.accounts[idx].name
        with suppress(Exception):
            _get_account_logger(chosen).info(
                "round-robin pick: idx=%d/%d (next=%d)", idx, len(self.accounts), nxt
            )
        return idx

    def generate_image(
        self,
        prompt: str,
        out_path: str | Path,
        *,
        compress: bool = True,
        max_size_mb: float = 1.0,
        generate_timeout_s: int = 240,
    ) -> dict:
        out_path = Path(out_path)
        n = len(self.accounts)
        start = self._next_index()
        last_err: Exception | None = None
        now = time.time()
        
        # Build ordered list of accounts, skipping those in extended cooldown
        ordered = []
        for offset in range(n):
            acc = self.accounts[(start + offset) % n]
            if acc.cooldown_until > now:
                remaining = int(acc.cooldown_until - now)
                _get_account_logger(acc.name).info(
                    "skip: extended cooldown (%ds remaining, %d consecutive fails)",
                    remaining, acc.fail_count
                )
                continue
            ordered.append(acc)
        
        if not ordered:
            # All accounts in cooldown — wait for the one with shortest cooldown
            shortest = min(self.accounts, key=lambda a: a.cooldown_until)
            wait_s = min(shortest.cooldown_until - now + 1, 30)
            _get_account_logger("pool").warning(
                "all accounts in cooldown, waiting %ds for %s", int(wait_s), shortest.name
            )
            time.sleep(wait_s)
            ordered = [shortest]
        
        for acc in ordered:
            try:
                # Per-account rate limit: minimum cooldown_s between requests
                elapsed_since_last = now - acc.last_request_time
                if elapsed_since_last < self.cooldown_s:
                    wait = self.cooldown_s - elapsed_since_last
                    _get_account_logger(acc.name).info("rate limit: wait %.1fs", wait)
                    time.sleep(wait)
                
                acc.launch(self._pw)
                res = acc.generate_image(prompt, out_path, generate_timeout_s=generate_timeout_s)
                
                # Success: reset fail counter, update health
                acc.fail_count = 0
                acc.success_count += 1
                acc.last_request_time = time.time()
                
                if compress and compress_image is not None:
                    try:
                        compress_image(out_path, max_size_mb=max_size_mb)
                        res["size_after_compress"] = out_path.stat().st_size
                    except Exception as e:
                        _get_account_logger(acc.name).warning("compress error (kept raw): %s", e)
                return res
            except Exception as e:
                last_err = e
                acc.fail_count += 1
                acc.last_request_time = time.time()
                _get_account_logger(acc.name).exception("job failed: %s", e)
                
                # Extended cooldown after too many consecutive fails
                if acc.fail_count >= self.max_consecutive_fails:
                    acc.cooldown_until = time.time() + self.extended_cooldown_s
                    _get_account_logger(acc.name).warning(
                        "%d consecutive fails → extended cooldown %ds",
                        acc.fail_count, int(self.extended_cooldown_s)
                    )
                
                _get_account_logger(acc.name).warning(
                    "%s failed (attempt %d): %s → trying next account", acc.name, acc.fail_count, e
                )
                # close akun ini supaya browser baru kalau retry
                acc.close()
                continue
        raise RuntimeError(f"Semua akun gagal. Last: {last_err}")


# ─────────────────────────────────────────────────────────────── CLI


def _resolve_path(p: str) -> Path:
    pp = Path(p)
    return pp if pp.is_absolute() else (REPO_DIR / pp)


def _cmd_check(pool: GeminiPool) -> int:
    for a in pool.accounts:
        try:
            a.launch(pool._pw)
            log.info(f"  ✓ {a.name} ({a.email or '-'}) – siap")
        except Exception as e:
            log.error(f"  ✗ {a.name}: {e}")
    return 0


def _cmd_single(pool: GeminiPool, prompt: str, out: Path, *, compress: bool, max_mb: float) -> int:
    log.info(f"Generate: {out}")
    res = pool.generate_image(prompt, out, compress=compress, max_size_mb=max_mb)
    log.info(f"  ✓ via {res['account']} ({res.get('email') or '-'}) – {res['size']//1024} KB")
    return 0


def _cmd_batch(
    pool: GeminiPool,
    prompts: list[dict],
    out_dir: Path,
    *,
    compress: bool,
    max_mb: float,
    overwrite: bool,
) -> int:
    ok = fail = 0
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, item in enumerate(prompts, 1):
        name = item.get("name") or f"image-{i:02d}.png"
        prompt = item.get("prompt") or ""
        if not prompt:
            log.warning(f"[{i}] skip — prompt kosong")
            fail += 1
            continue
        out = out_dir / name
        log.info(f"\n[{i}/{len(prompts)}] {name}")
        if out.exists() and not overwrite:
            log.info("  • file sudah ada – skip")
            ok += 1
            continue
        try:
            res = pool.generate_image(prompt, out, compress=compress, max_size_mb=max_mb)
            log.info(
                f"  ✓ via {res['account']} ({res.get('email') or '-'}) – {out.stat().st_size//1024} KB"
            )
            ok += 1
        except Exception as e:
            log.error(f"  ✗ {e}")
            fail += 1
    log.info(f"\nSummary: OK={ok} FAIL={fail}")
    return 0 if fail == 0 else 3


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", help="Prompt single-shot")
    parser.add_argument("--out", help="Output path (untuk --prompt)")
    parser.add_argument("--prompts-json", help="JSON file: [{name, prompt}, …]")
    parser.add_argument(
        "--out-dir",
        default=str(REPO_DIR.parent / "data" / "image"),
        help="Output directory untuk --prompts-json",
    )
    parser.add_argument("--check", action="store_true", help="Cek pool akun lalu exit")
    parser.add_argument("--no-compress", action="store_true", help="Jangan compress hasil")
    parser.add_argument("--max-size-mb", type=float, default=1.0)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    # Configure logging for CLI usage
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    with GeminiPool.from_env() as pool:
        log.info(f"Pool: {len(pool.accounts)} akun → {[a.name for a in pool.accounts]}")
        if args.check:
            return _cmd_check(pool)
        if args.prompt:
            if not args.out:
                raise SystemExit("--prompt butuh --out")
            return _cmd_single(
                pool,
                args.prompt,
                _resolve_path(args.out),
                compress=not args.no_compress,
                max_mb=args.max_size_mb,
            )
        if args.prompts_json:
            data = json.loads(_resolve_path(args.prompts_json).read_text(encoding="utf-8"))
            return _cmd_batch(
                pool,
                data,
                _resolve_path(args.out_dir),
                compress=not args.no_compress,
                max_mb=args.max_size_mb,
                overwrite=args.overwrite,
            )
        parser.print_help()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
