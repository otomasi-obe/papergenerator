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
    from imageGenerator.CreateImageGemini import GeminiPool

    with GeminiPool.from_env() as pool:
        pool.generate_image("a futuristic city", "out.png")
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
import sys
import time
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import sync_playwright
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass

try:
    from compress import compress_image
except Exception:
    compress_image = None  # type: ignore


REPO_DIR = Path(__file__).resolve().parent
RR_STATE_PATH = REPO_DIR / ".rr-state.json"
GEMINI_URL = "https://gemini.google.com/app"
DEFAULT_VIEWPORT = (1536, 864)
DOWNLOAD_BTN_RE = re.compile(
    r"^(Download|Unduh)\b.*\b(gambar|image)\b", re.IGNORECASE
)


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
            f"""(sel) => {{
                const b = [...document.querySelectorAll(sel)].find(x => !x.disabled);
                if (b) {{ b.click(); return true; }}
                return false;
            }}""",
            sel,
        )
    )


def _open_image_tool(page) -> None:
    """Buka menu 'Upload & alat' lalu pilih item 'Gambar'."""
    # cek apakah mode image sudah aktif
    if page.locator(
        'button[aria-label*="Buat Gambar"], button[aria-label*="Create image"]'
    ).count() > 0:
        return

    if not _click_via_js(page, ["Upload & alat", "Upload & tools"]):
        raise RuntimeError("Tidak bisa membuka menu 'Upload & alat'")
    page.wait_for_timeout(800)

    selected = page.evaluate(
        """() => {
            for (const el of document.querySelectorAll('[role="menuitemcheckbox"]')) {
                const t = (el.getAttribute('aria-label') || el.textContent || '').toLowerCase();
                if (t.includes('gambar') || t.includes('image')) {
                    el.click();
                    return true;
                }
            }
            return false;
        }"""
    )
    if not selected:
        raise RuntimeError("Tidak menemukan menu item 'Gambar' di Upload & alat")
    page.wait_for_timeout(1500)


def _send_prompt(page, prompt: str) -> None:
    box = page.locator('div[contenteditable="true"]').first
    box.click(timeout=15_000)
    box.fill(prompt)
    page.wait_for_timeout(500)
    if not _click_via_js(page, ["Kirim pesan", "Send message"]):
        # fallback: keyboard Enter
        box.press("Enter")


def _wait_download_button(page, *, timeout_s: int) -> object:
    deadline = time.monotonic() + timeout_s
    next_log = time.monotonic() + 15
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
            print(
                f"      … menunggu image (elapsed {int(time.monotonic() - (deadline - timeout_s))}s/{timeout_s}s)",
                flush=True,
            )
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
        self.context = p.chromium.launch_persistent_context(
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
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.on("response", self._on_response)
        self.page.goto(GEMINI_URL, wait_until="domcontentloaded")
        self.page.wait_for_timeout(4000)

    def _on_response(self, resp) -> None:
        try:
            url = resp.url
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
        """Buka chat baru supaya tombol download lama tidak ikut ter-pick."""
        if self.page is None:
            return
        with suppress(Exception):
            self.page.goto(GEMINI_URL, wait_until="domcontentloaded")
            self.page.wait_for_timeout(2000)

    def generate_image(self, prompt: str, out_path: Path, *, generate_timeout_s: int = 240) -> dict:
        """Generate satu gambar lalu simpan ke out_path. Tidak return sampai file ada di disk."""
        if self.page is None:
            raise RuntimeError(f"{self.name}: launch() belum dipanggil")
        page = self.page

        # Reset ke chat baru supaya hanya ada 1 image yang baru di-generate.
        if self.requests_made > 0:
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
        if img_bytes is None or not _looks_like_image(img_bytes):
            deadline = time.time() + 60
            collected_redirect: str | None = None
            while time.time() < deadline and (img_bytes is None or not _looks_like_image(img_bytes)):
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
            raise RuntimeError("Gagal capture image bytes (intercept timeout)")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(img_bytes)
        self.requests_made += 1
        return {"path": str(out_path), "account": self.name, "email": self.email, "size": len(img_bytes)}


@dataclass
class GeminiPool:
    accounts: list[GeminiAccount]
    state_path: Path = RR_STATE_PATH
    cooldown_s: float = 4.0  # delay setelah generate per akun

    _pw_cm: object | None = field(default=None, repr=False)
    _pw: object | None = field(default=None, repr=False)

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
            self.state_path.write_text(
                json.dumps({"next": nxt, "updated_at": time.time()}), encoding="utf-8"
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
        for offset in range(n):
            acc = self.accounts[(start + offset) % n]
            try:
                acc.launch(self._pw)
                res = acc.generate_image(prompt, out_path, generate_timeout_s=generate_timeout_s)
                if compress and compress_image is not None:
                    try:
                        compress_image(out_path, max_size_mb=max_size_mb)
                        res["size_after_compress"] = out_path.stat().st_size
                    except Exception as e:
                        print(f"  ! compress error (kept raw): {e}")
                if self.cooldown_s > 0:
                    time.sleep(self.cooldown_s)
                return res
            except Exception as e:
                last_err = e
                print(f"  ! {acc.name} gagal: {e} → coba akun berikutnya", flush=True)
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
            print(f"  ✓ {a.name} ({a.email or '-'}) – siap")
        except Exception as e:
            print(f"  ✗ {a.name}: {e}")
    return 0


def _cmd_single(pool: GeminiPool, prompt: str, out: Path, *, compress: bool, max_mb: float) -> int:
    print(f"Generate: {out}")
    res = pool.generate_image(prompt, out, compress=compress, max_size_mb=max_mb)
    print(f"  ✓ via {res['account']} ({res.get('email') or '-'}) – {res['size']//1024} KB")
    return 0


def _cmd_batch(pool: GeminiPool, prompts: list[dict], out_dir: Path, *, compress: bool, max_mb: float, overwrite: bool) -> int:
    ok = fail = 0
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, item in enumerate(prompts, 1):
        name = item.get("name") or f"image-{i:02d}.png"
        prompt = item.get("prompt") or ""
        if not prompt:
            print(f"[{i}] skip — prompt kosong"); fail += 1; continue
        out = out_dir / name
        print(f"\n[{i}/{len(prompts)}] {name}")
        if out.exists() and not overwrite:
            print("  • file sudah ada – skip"); ok += 1; continue
        try:
            res = pool.generate_image(prompt, out, compress=compress, max_size_mb=max_mb)
            print(f"  ✓ via {res['account']} ({res.get('email') or '-'}) – {out.stat().st_size//1024} KB")
            ok += 1
        except Exception as e:
            print(f"  ✗ {e}"); fail += 1
    print(f"\nSummary: OK={ok} FAIL={fail}")
    return 0 if fail == 0 else 3


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", help="Prompt single-shot")
    parser.add_argument("--out", help="Output path (untuk --prompt)")
    parser.add_argument("--prompts-json", help="JSON file: [{name, prompt}, …]")
    parser.add_argument("--out-dir", default=str(REPO_DIR.parent / "image"), help="Output directory untuk --prompts-json")
    parser.add_argument("--check", action="store_true", help="Cek pool akun lalu exit")
    parser.add_argument("--no-compress", action="store_true", help="Jangan compress hasil")
    parser.add_argument("--max-size-mb", type=float, default=1.0)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    with GeminiPool.from_env() as pool:
        print(f"Pool: {len(pool.accounts)} akun → {[a.name for a in pool.accounts]}")
        if args.check:
            return _cmd_check(pool)
        if args.prompt:
            if not args.out:
                raise SystemExit("--prompt butuh --out")
            return _cmd_single(pool, args.prompt, _resolve_path(args.out), compress=not args.no_compress, max_mb=args.max_size_mb)
        if args.prompts_json:
            data = json.loads(_resolve_path(args.prompts_json).read_text(encoding="utf-8"))
            return _cmd_batch(pool, data, _resolve_path(args.out_dir), compress=not args.no_compress, max_mb=args.max_size_mb, overwrite=args.overwrite)
        parser.print_help()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
