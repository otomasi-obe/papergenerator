"""Helper script to compress Gemini-generated images.

Run this after downloading images to the `gambar/` folder.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image


def _get_size_bytes(path: Path) -> int:
    return path.stat().st_size


def _bytes_to_kb(size_bytes: int) -> float:
    return size_bytes / 1024


def _to_rgb_with_white_bg(img: Image.Image) -> Image.Image:
    """Ensure RGB image (flatten alpha/palette on white background when needed)."""
    if img.mode in ("RGBA", "LA"):
        rgba = img.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        background.alpha_composite(rgba)
        return background.convert("RGB")
    if img.mode == "P":
        if "transparency" in img.info:
            return _to_rgb_with_white_bg(img.convert("RGBA"))
        return img.convert("RGB")
    if img.mode != "RGB":
        return img.convert("RGB")
    return img


def _compress_jpeg_inplace(image_path: Path, max_size_bytes: int) -> bool:
    with Image.open(image_path) as img:
        img = _to_rgb_with_white_bg(img)

        quality = 85
        while quality >= 20:
            output = BytesIO()
            img.save(output, format="JPEG", quality=quality, optimize=True)
            data = output.getvalue()
            if len(data) <= max_size_bytes:
                image_path.write_bytes(data)
                file_size = _get_size_bytes(image_path)
                print(f"  ✓ Berhasil: {_bytes_to_kb(file_size):.1f} KB (JPEG quality: {quality})")
                return True
            quality -= 5

        print("  ✗ Gagal kompres JPEG ke < 1MB")
        return False


def _try_png_save(img: Image.Image, *, colors: int | None, compress_level: int) -> bytes:
    out = BytesIO()

    save_img = img
    if colors is not None:
        rgb = _to_rgb_with_white_bg(img)
        save_img = rgb.quantize(
            colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
        )

    save_img.save(out, format="PNG", optimize=True, compress_level=compress_level)
    return out.getvalue()


def _compress_png_inplace(image_path: Path, max_size_bytes: int) -> bool:
    with Image.open(image_path) as img:
        original_w, original_h = img.size

        # Strategy:
        # 1) optimize PNG with max compression
        # 2) quantize (great for diagrams)
        # 3) if needed, downscale gradually + quantize
        candidates: list[tuple[float, int | None]] = []
        candidates.append((1.0, None))
        for c in (256, 128, 64):
            candidates.append((1.0, c))

        for scale in (0.9, 0.8, 0.7, 0.6):
            for c in (256, 128):
                candidates.append((scale, c))

        for scale, colors in candidates:
            working = img
            if scale != 1.0:
                new_w = max(1, int(original_w * scale))
                new_h = max(1, int(original_h * scale))
                working = img.resize((new_w, new_h), resample=Image.Resampling.LANCZOS)

            data = _try_png_save(working, colors=colors, compress_level=9)
            if len(data) <= max_size_bytes:
                image_path.write_bytes(data)
                file_size = _get_size_bytes(image_path)
                note = []
                if scale != 1.0:
                    note.append(f"scale: {scale:.1f}")
                if colors is not None:
                    note.append(f"colors: {colors}")
                note_str = f" ({', '.join(note)})" if note else ""
                print(f"  ✓ Berhasil: {_bytes_to_kb(file_size):.1f} KB (PNG){note_str}")
                return True

        print("  ✗ Gagal kompres PNG ke < 1MB")
        return False


def compress_image(image_path: str | Path, max_size_mb: float = 1.0) -> bool:
    """Compress image to be under max_size_mb (in-place, preserving extension)."""
    path = Path(image_path)
    # Use decimal MB (1 MB = 1,000,000 bytes) to match common upload limits.
    max_size_bytes = int(max_size_mb * 1_000_000)

    file_size = _get_size_bytes(path)
    if file_size <= max_size_bytes:
        print(f"  ✓ Ukuran OK: {_bytes_to_kb(file_size):.1f} KB")
        return True

    print(f"  Kompres: {_bytes_to_kb(file_size):.1f} KB → {max_size_mb}MB")

    suffix = path.suffix.lower()
    try:
        if suffix in {".jpg", ".jpeg"}:
            return _compress_jpeg_inplace(path, max_size_bytes)
        if suffix == ".png":
            return _compress_png_inplace(path, max_size_bytes)

        print(f"  ✗ Skip: format {suffix} belum didukung")
        return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def main():
    gambar_dir = Path("gambar")

    if not gambar_dir.exists():
        print(f"✗ Direktori {gambar_dir}/ tidak ditemukan")
        return

    image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
    images = [f for f in gambar_dir.glob("*") if f.suffix.lower() in image_extensions]

    if not images:
        print("✗ Tidak ada gambar di gambar/ folder")
        return

    print(f"{'='*70}")
    print("COMPRESS IMAGES FROM GEMINI")
    print(f"{'='*70}")
    print(f"Found {len(images)} images\n")

    for image_path in images:
        print(f"Processing: {image_path.name}")
        compress_image(str(image_path))

    print(f"\n{'='*70}")
    print(f"✓ Done! {len(images)} images diproses")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
