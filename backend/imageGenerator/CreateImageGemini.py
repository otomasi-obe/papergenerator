"""Generate gambar Gemini via Playwright UI (round-robin 4 akun).

Kenapa pakai Playwright, bukan HTTP API langsung
- URL gambar Gemini berformat https://lh3.googleusercontent.com/gg-dl/... — itu
  signed download token yang umur sangat pendek dan harus dipicu lewat browser
  flow (`page.expect_download`); GET biasa balas 404.
- Profile per akun (`imageGenerator/account{N}`) sudah login penuh dari
  GeminiCookies.py, jadi tinggal di-pakai oleh Playwright persistent context.

Pakai sebagai library
    from imageGenerator.CreateImageGemini import GeminiPool

    with GeminiPool.from_env() as pool:
        pool.generate_image("a futuristic city", "out.png")
        pool.generate_image("rainforest at dusk", "out2.png")

    # konteks per akun ditutup otomatis di __exit__.

Pakai sebagai CLI
    python CreateImageGemini.py --prompt "kucing astronot" --out out.png
    python CreateImageGemini.py --review-json review.json
    python CreateImageGemini.py --check        # validasi tiap akun terbuka & login
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from playwright.sync_api import sync_playwright, Browser
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass


REPO_DIR = Path(__file__).resolve().parent
RR_STATE_PATH = REPO_DIR / ".rr-state.json"
DEFAULT_URL = "https://gemini.google.com/app"
DEFAULT_VIEWPORT = (1536, 864)


# ───────────────────────────────────────────────────────────────────── helpers

class BrowserClosedError(RuntimeError):
    pass


def _is_target_closed_error(exc: BaseException) -> bool:
    msg = str(exc)
    return (
        "Target page, context or browser has been closed" in msg
        or "TargetClosedError" in msg
        or ("has been closed" in msg and "Target" in msg)
    )


def _is_logged_in(page) -> tuple[bool, str | None]:
    try:
        for pat in (r"Akun Google", r"Google Account"):
            loc = page.get_by_role("button", name=re.compile(pat, re.IGNORECASE))
            if loc.count() > 0:
                label = loc.first.get_attribute("aria-label") or ""
                if not label:
                    with suppress(Exception):
                        label = loc.first.inner_text(timeout=500) or ""
                return True, label.strip() or None
    except Exception:
        pass

    composer = page.get_by_role(
        "textbox",
        name=re.compile(
            r"Masukkan perintah|Minta Gemini|Ask Gemini|Type a prompt|Enter a prompt|"
            r"Deskripsikan gambar|Describe your image",
            re.IGNORECASE,
        ),
    )
    if composer.count() > 0:
        return True, None
    return False, None


def _dismiss_obstructing_dialogs(page) -> None:
    with suppress(Exception):
        close_btn = page.locator('[data-test-id="close-button"]')
        if close_btn.count() > 0:
            close_btn.first.click(timeout=1000)
            page.wait_for_timeout(150)
            return
    for pat in (r"Lain\s+kali", r"Not\s+now", r"Tutup", r"Close"):
        with suppress(Exception):
            btn = page.get_by_role("button", name=re.compile(pat, re.IGNORECASE))
            if btn.count() > 0:
                btn.first.click(timeout=1000)
                page.wait_for_timeout(150)
                return


def _ensure_gemini_image_tool_selected(page) -> None:
    cancel = page.get_by_role(
        "button",
        name=re.compile(
            r"Batalkan pilihan\s+Buat\s+Gambar|Cancel selection\s+Create image",
            re.IGNORECASE,
        ),
    )
    with suppress(Exception):
        cancel.wait_for(state="visible", timeout=800)
        return

    tool_btn = page.get_by_role(
        "button",
        name=re.compile(r"Buat\s*gambar|Create\s*image", re.IGNORECASE),
    )
    if tool_btn.count() > 0:
        tool_btn.first.click()
        with suppress(Exception):
            cancel.wait_for(state="visible", timeout=5_000)
            return

    tools_btn = page.get_by_role("button", name=re.compile(r"\bAlat\b|\bTools\b", re.IGNORECASE))
    if tools_btn.count() > 0:
        tools_btn.first.click()
        page.wait_for_timeout(200)
        for role in ("menuitem", "button"):
            pick = page.get_by_role(role, name=re.compile(r"Buat\s*Gambar|Create\s*image", re.IGNORECASE))
            if pick.count() > 0:
                pick.first.click()
                with suppress(Exception):
                    cancel.wait_for(state="visible", timeout=5_000)
                    return

    raise RuntimeError("Tidak bisa memilih tool 'Buat gambar' di Gemini")


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
        with suppress(Exception):
            if loc.count() > 0:
                return loc.first
    raise RuntimeError("Tidak menemukan textbox prompt di Gemini")


def _send_prompt(page, prompt: str) -> None:
    box = _find_prompt_textbox(page)
    box.click()
    box.fill(prompt)
    send = page.get_by_role("button", name=re.compile(r"Kirim|Send", re.IGNORECASE))
    if send.count() > 0:
        send.last.click()
        return
    box.press("Enter")


_DOWNLOAD_FULL_SIZE_RE = re.compile(r"^(Download|Unduh)\b.*\b(gambar|image)\b", re.IGNORECASE)


def _download_full_size_buttons(page):
    return page.get_by_role("button", name=_DOWNLOAD_FULL_SIZE_RE)


def _wait_for_new_download_button(page, *, previous_count: int, timeout_ms: int):
    buttons = _download_full_size_buttons(page)
    started = time.monotonic()
    deadline = started + timeout_ms / 1000
    next_log = started + 10
    while time.monotonic() < deadline:
        try:
            count = buttons.count()
        except Exception:
            count = 0
        if count > previous_count:
            cand = buttons.nth(previous_count)
            with suppress(Exception):
                cand.wait_for(state="visible", timeout=2_000)
            return cand
        now = time.monotonic()
        if now >= next_log:
            elapsed = int(now - started)
            total = max(1, int(timeout_ms / 1000))
            print(f"      … menunggu tombol download (elapsed {elapsed}s/{total}s, btn before={previous_count} now={count})", flush=True)
            next_log = now + 10
        page.wait_for_timeout(500)
    raise RuntimeError("Tombol download baru tidak muncul (timeout)")


def _download_new_image(page, out_path: Path, *, previous_download_count: int, timeout_ms: int) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    stop_btn = page.get_by_role(
        "button",
        name=re.compile(r"Hentikan\s+respons|Stop\s+response|Stop\s+generating", re.IGNORECASE),
    )
    saw_stop = False
    try:
        stop_btn.wait_for(state="visible", timeout=min(10_000, timeout_ms))
        saw_stop = True
    except PlaywrightTimeoutError:
        pass

    if saw_stop:
        next_log = time.monotonic() + 10
        while True:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            remaining = timeout_ms - elapsed_ms
            if remaining <= 0:
                raise RuntimeError("Timeout menunggu Gemini selesai generate")
            try:
                stop_btn.wait_for(state="hidden", timeout=min(5_000, remaining))
                break
            except PlaywrightTimeoutError:
                if time.monotonic() >= next_log:
                    print(f"      … masih generating ({int(elapsed_ms/1000)}s)", flush=True)
                    next_log = time.monotonic() + 10
                continue

    elapsed_ms = int((time.monotonic() - started) * 1000)
    remaining = max(1, timeout_ms - elapsed_ms)
    fast = min(30_000, remaining) if saw_stop else remaining
    control = _wait_for_new_download_button(page, previous_count=previous_download_count, timeout_ms=fast)

    with suppress(Exception):
        control.scroll_into_view_if_needed(timeout=2000)

    elapsed_ms = int((time.monotonic() - started) * 1000)
    remaining = max(1, timeout_ms - elapsed_ms)
    try:
        with page.expect_download(timeout=remaining) as d:
            control.click()
        d.value.save_as(str(out_path))
        return
    except Exception:
        with suppress(Exception):
            control.click(timeout=2000)
            page.wait_for_timeout(200)
        for loc in (
            page.get_by_role("menuitem", name=_DOWNLOAD_FULL_SIZE_RE),
            page.get_by_role("link", name=_DOWNLOAD_FULL_SIZE_RE),
            page.get_by_role("menuitem", name=re.compile(r"download|unduh", re.IGNORECASE)),
        ):
            with suppress(Exception):
                item = loc.last
                if item.count() > 0:
                    with page.expect_download(timeout=remaining) as d2:
                        item.click()
                    d2.value.save_as(str(out_path))
                    return
        raise


# ───────────────────────────────────────────────────────────────────── pool

@dataclass
class GeminiAccount:
    name: str
    user_data_dir: Path
    email: str | None = None

    context: object | None = field(default=None, repr=False)
    page: object | None = field(default=None, repr=False)

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
                f"Profile akun {slot_name} tidak ada: {user_data_dir}. "
                "Jalankan GeminiCookies.py untuk login dulu."
            )
        email = os.environ.get(f"GEMINI_ACCOUNT{n}_EMAIL")
        return cls(name=slot_name, user_data_dir=user_data_dir, email=email)

    def launch(self, p) -> None:
        if self.context is not None:
            return
        ctx_kwargs = dict(
            user_data_dir=str(self.user_data_dir),
            channel="chrome",
            headless=False,
            accept_downloads=True,
            viewport={"width": DEFAULT_VIEWPORT[0], "height": DEFAULT_VIEWPORT[1]},
            args=[
                "--profile-directory=Default",
                "--no-first-run",
                "--no-default-browser-check",
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--lang=en-US,en",
            ],
            ignore_default_args=["--enable-automation"],
            timezone_id="Asia/Bangkok",
        )
        self.context = p.chromium.launch_persistent_context(**ctx_kwargs)
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.goto(DEFAULT_URL, wait_until="domcontentloaded")
        self.page.wait_for_timeout(1500)

        ok, _ = _is_logged_in(self.page)
        if not ok:
            raise RuntimeError(
                f"{self.name}: profile tidak dalam keadaan login. "
                "Re-run GeminiCookies.py --slot {N} --refresh."
            )

    def close(self) -> None:
        if self.context is not None:
            with suppress(Exception):
                self.context.close()
            self.context = None
            self.page = None


@dataclass
class GeminiPool:
    accounts: list[GeminiAccount]
    state_path: Path = RR_STATE_PATH

    _pw: object | None = field(default=None, repr=False)
    _pw_cm: object | None = field(default=None, repr=False)

    @classmethod
    def from_env(cls) -> "GeminiPool":
        names_env = os.environ.get("GEMINI_PROFILES", "account1,account2,account3,account4")
        names = [n.strip() for n in names_env.split(",") if n.strip()]
        accounts: list[GeminiAccount] = []
        for n in names:
            try:
                accounts.append(GeminiAccount.from_env(n))
            except Exception as e:
                print(f"! skip {n}: {e}", file=sys.stderr)
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
        for a in self.accounts:
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
            self.state_path.write_text(json.dumps({"next": nxt, "updated_at": time.time()}), encoding="utf-8")
        return idx

    def _generate_with_account(self, acc: GeminiAccount, prompt: str, out_path: Path, *, timeout_ms: int) -> dict:
        acc.launch(self._pw)
        page = acc.page
        _dismiss_obstructing_dialogs(page)
        _ensure_gemini_image_tool_selected(page)

        try:
            prev_count = _download_full_size_buttons(page).count()
        except Exception as e:
            if _is_target_closed_error(e):
                raise BrowserClosedError(str(e)) from e
            prev_count = 0

        max_attempts = 3
        last_err: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            attempt_prompt = prompt if attempt == 1 else f"{prompt}\n\n+ tolong buatkan gambar"
            _send_prompt(page, attempt_prompt)
            try:
                _download_new_image(page, out_path, previous_download_count=prev_count, timeout_ms=timeout_ms)
                last_err = None
                break
            except Exception as e:
                if _is_target_closed_error(e):
                    raise BrowserClosedError(str(e)) from e
                last_err = e
                if attempt < max_attempts:
                    print(f"      ! attempt {attempt} gagal ({e}); retry dengan hint", flush=True)
                    prev_count = _download_full_size_buttons(page).count()
                    continue
                raise

        if last_err is not None:
            raise last_err

        return {
            "path": str(out_path),
            "account": acc.name,
            "email": acc.email,
        }

    def generate_image(self, prompt: str, out_path: str | Path, *, timeout_ms: int = 180_000) -> dict:
        out_path = Path(out_path)
        n = len(self.accounts)
        start = self._next_index()
        last_err: Exception | None = None
        for offset in range(n):
            acc = self.accounts[(start + offset) % n]
            try:
                return self._generate_with_account(acc, prompt, out_path, timeout_ms=timeout_ms)
            except BrowserClosedError as e:
                last_err = e
                acc.close()
                print(f"  ! {acc.name} browser tertutup, coba akun berikutnya", flush=True)
                continue
            except Exception as e:
                last_err = e
                print(f"  ! {acc.name} gagal: {e} → coba akun berikutnya", flush=True)
                continue
        raise RuntimeError(f"Semua akun gagal generate. Last error: {last_err}")


# ───────────────────────────────────────────────────────────────────── CLI

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
    items.sort(
        key=lambda i: (int(i.get("ImageNumber") or 10**9) if str(i.get("ImageNumber") or "").isdigit() else 10**9)
    )
    return items


def _resolve_path(p: str) -> Path:
    pp = Path(p)
    return pp if pp.is_absolute() else (REPO_DIR / pp)


def _cmd_review(pool: GeminiPool, review_json: Path, *, only: set[str] | None, overwrite: bool) -> int:
    items = _extract_review_image_items(json.loads(review_json.read_text(encoding="utf-8")))
    if only:
        items = [i for i in items if str(i.get("ImageNumber")) in only]
    if not items:
        print("Tidak ada entry gambar di review.json")
        return 1

    ok = fail = 0
    for it in items:
        num = it.get("ImageNumber")
        out = _resolve_path(it["Path"])
        prompt = it["Prompt"]
        title = it.get("Title", "")
        print(f"\n--- Image {num}: {title}\n  → {out}")
        if out.exists() and not overwrite:
            print("  • file sudah ada – skip (pakai --overwrite untuk replace)")
            ok += 1
            continue
        try:
            res = pool.generate_image(prompt, out)
            print(f"  ✓ via {res['account']} ({res.get('email') or '-'})")
            ok += 1
        except Exception as e:
            print(f"  ✗ {e}")
            fail += 1

    print(f"\nDone. OK={ok} FAIL={fail}")
    return 0 if fail == 0 else 3


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", help="Prompt single-shot (pakai bersama --out)")
    parser.add_argument("--out", help="Output path untuk --prompt")
    parser.add_argument("--review-json", help="Path review.json untuk batch generate")
    parser.add_argument("--only-images", help="Comma list ImageNumber yang di-generate")
    parser.add_argument("--overwrite", action="store_true", help="Timpa file yang sudah ada")
    parser.add_argument("--check", action="store_true", help="Buka tiap profile lalu cek login state")
    parser.add_argument("--timeout-ms", type=int, default=180_000, help="Timeout per generate (default 180000)")
    args = parser.parse_args()

    with GeminiPool.from_env() as pool:
        print(f"Pool: {len(pool.accounts)} akun → {[a.name for a in pool.accounts]}")

        if args.check:
            for a in pool.accounts:
                try:
                    a.launch(pool._pw)
                    print(f"  ✓ {a.name} ({a.email or '-'}) – login OK")
                except Exception as e:
                    print(f"  ✗ {a.name}: {e}")
            return 0

        if args.prompt:
            if not args.out:
                raise SystemExit("--prompt butuh --out")
            res = pool.generate_image(args.prompt, args.out, timeout_ms=args.timeout_ms)
            print(json.dumps(res, indent=2, ensure_ascii=False))
            return 0

        if args.review_json:
            only = {s.strip() for s in args.only_images.split(",")} if args.only_images else None
            return _cmd_review(pool, _resolve_path(args.review_json), only=only, overwrite=args.overwrite)

        parser.print_help()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
