import argparse
import os
import re
import sys
import textwrap
import time
from collections import defaultdict

import fitz

# Force UTF-8 for stdout/stderr so Unicode chars (→ ← • etc.) never cause
# 'charmap' codec errors on Windows (where default encoding is cp1252).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

NOISE_LINE_PATTERNS = (
    "Authorized licensed use limited to:",
    "Restrictions apply.",
)

MAX_OUTPUT_LINE_WIDTH = 70
CONTINUATION_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "because",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "these",
    "this",
    "to",
    "using",
    "while",
    "with",
}


def _normalize_text(text: str) -> str:
    text = text.replace("\xa0", " ").replace("\u00ad", "-")
    text = text.replace("\u2010", "-").replace("\u2011", "-")
    return re.sub(r"\s+", " ", text).strip()


def _is_noise_line(text: str) -> bool:
    if not text:
        return True
    if any(pattern in text for pattern in NOISE_LINE_PATTERNS):
        return True
    if len(text) <= 3 and not re.search(r"\d", text):
        return True
    if re.fullmatch(r"[|•.\-_/\\]+", text):
        return True
    return False


def _collect_font_stats(doc: fitz.Document) -> dict[str, dict[str, int]]:
    stats: dict[str, dict[str, int]] = defaultdict(
        lambda: {"chars": 0, "alpha": 0, "lower": 0, "upper": 0, "digits": 0, "spans": 0}
    )

    for page in doc:
        page_dict = page.get_text("dict")
        for block in page_dict.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    if not text.strip():
                        continue
                    font = span.get("font", "")
                    stat = stats[font]
                    stat["chars"] += len(text)
                    stat["alpha"] += sum(ch.isalpha() for ch in text)
                    stat["lower"] += sum(ch.islower() for ch in text)
                    stat["upper"] += sum(ch.isupper() for ch in text)
                    stat["digits"] += sum(ch.isdigit() for ch in text)
                    stat["spans"] += 1

    return stats


def _is_corrupt_font(stat: dict[str, int]) -> bool:
    if stat["chars"] < 500:
        return False

    alpha = max(stat["alpha"], 1)
    char_count = max(stat["chars"], 1)
    lower_ratio = stat["lower"] / alpha
    upper_ratio = stat["upper"] / alpha
    digit_ratio = stat["digits"] / char_count

    return lower_ratio < 0.05 and upper_ratio > 0.85 and digit_ratio > 0.03


def _join_wrapped_lines(lines: list[str]) -> str:
    paragraph = []
    for line in lines:
        if not paragraph:
            paragraph.append(line)
            continue

        if paragraph[-1].endswith("-") and line and line[0].islower():
            paragraph[-1] = paragraph[-1][:-1] + line
        else:
            paragraph.append(line)

    return " ".join(paragraph)


def _is_heading_line(text: str) -> bool:
    if not text:
        return False
    if re.match(r"^\d+(?:\.\d+)*\.?(?:\s+[A-Z].*)?$", text):
        return True
    if re.match(
        r"^(abstract|keywords?|references?|conclusion|introduction|methodology|results?|discussion)\b",
        text,
        re.I,
    ):
        return True
    return text.isupper() and len(text.split()) <= 8


def _is_tabular_line(text: str) -> bool:
    alpha = sum(ch.isalpha() for ch in text)
    digits = sum(ch.isdigit() for ch in text)
    return digits >= alpha and digits > 0


def _is_sentence_like(text: str) -> bool:
    if not text or "@" in text or _is_heading_line(text):
        return False
    if re.match(r"^(fig\.?|table|model|keywords?:)\b", text, re.I):
        return False
    words = text.split()
    alpha = sum(ch.isalpha() for ch in text)
    return len(words) >= 4 and alpha >= 20 and not _is_tabular_line(text)


def _is_tabular_block(lines: list[str]) -> bool:
    if not lines:
        return False
    numeric_lines = sum(1 for line in lines if _is_tabular_line(line))
    return numeric_lines >= max(2, len(lines) // 3)


def _wrap_output_text(text: str) -> list[str]:
    wrapped = textwrap.wrap(
        text,
        width=MAX_OUTPUT_LINE_WIDTH,
        break_long_words=False,
        break_on_hyphens=False,
    )
    return wrapped or [text]


def _should_merge_items(previous: str, current: str) -> bool:
    if not (_is_sentence_like(previous) and _is_sentence_like(current)):
        return False
    if previous.endswith("-"):
        return True

    previous_last_word = previous.rstrip().split()[-1].strip("()[]{}\"'.,;:").lower()
    if previous_last_word in CONTINUATION_WORDS:
        return True

    return not re.search(r"[.!?:]$", previous)


def _merge_page_items(items: list[str]) -> list[str]:
    merged: list[str] = []
    for item in items:
        if not item:
            continue
        normalized = _normalize_text(item)
        if not normalized:
            continue

        if not merged or not _should_merge_items(merged[-1], normalized):
            merged.append(normalized)
            continue

        if merged[-1].endswith("-") and normalized[:1].islower():
            merged[-1] = merged[-1][:-1] + normalized
        else:
            merged[-1] = f"{merged[-1]} {normalized}"

    return merged


def _primary_font(fonts: list[str]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for font in fonts:
        counts[font] += 1
    if not counts:
        return ""
    return max(counts.items(), key=lambda item: item[1])[0]


def _can_merge_blocks(previous: dict, current: dict) -> bool:
    if previous.get("structured") or current.get("structured"):
        return False
    if previous.get("primary_font") != current.get("primary_font"):
        return False

    prev_x0, prev_y0, _, prev_y1 = previous["bbox"]
    curr_x0, curr_y0, _, _ = current["bbox"]

    same_column = abs(curr_x0 - prev_x0) <= 20
    vertical_gap = curr_y0 - prev_y1
    small_gap_same_column = same_column and 0 <= vertical_gap <= 8

    column_wrap = (
        curr_x0 - prev_x0 >= 120
        and curr_y0 < prev_y0
        and not re.search(r"[.!?:]$", previous["lines"][-1])
    )

    return small_gap_same_column or column_wrap


def _render_block(lines: list[str]) -> list[str]:
    if not lines:
        return []

    cleaned_lines: list[str] = []
    for line in lines:
        normalized = _normalize_text(line)
        if not normalized or _is_noise_line(normalized):
            continue
        if cleaned_lines and cleaned_lines[-1] == normalized:
            continue
        cleaned_lines.append(normalized)

    if not cleaned_lines:
        return []
    if any("@" in line for line in cleaned_lines):
        return cleaned_lines
    if len(cleaned_lines) == 1:
        return cleaned_lines
    if _is_heading_line(cleaned_lines[0]) and len(cleaned_lines) <= 3:
        return [" ".join(cleaned_lines)]
    if _is_tabular_block(cleaned_lines):
        return cleaned_lines

    return [_join_wrapped_lines(cleaned_lines)]


def _compact_text_lines(text: str) -> str:
    compact_lines: list[str] = []
    for raw_line in text.splitlines():
        line = _normalize_text(raw_line)
        if not line:
            continue
        compact_lines.append(line)
    return "\n".join(compact_lines).strip()


def _extract_filtered_text(pdf_path: str) -> tuple[list[str], list[str]]:
    doc = fitz.open(pdf_path)
    try:
        font_stats = _collect_font_stats(doc)
        corrupt_fonts = {font for font, stat in font_stats.items() if _is_corrupt_font(stat)}

        pages: list[str] = []
        for page in doc:
            page_dict = page.get_text("dict")
            raw_blocks: list[dict] = []

            for block in page_dict.get("blocks", []):
                block_lines: list[str] = []
                block_fonts: list[str] = []
                for line in block.get("lines", []):
                    parts: list[str] = []
                    for span in line.get("spans", []):
                        font = span.get("font", "")
                        if font in corrupt_fonts:
                            continue
                        text = span.get("text", "")
                        if text.strip():
                            parts.append(text)
                            block_fonts.append(font)

                    line_text = _normalize_text("".join(parts))
                    if _is_noise_line(line_text):
                        continue
                    block_lines.append(line_text)

                if not block_lines:
                    continue

                raw_blocks.append(
                    {
                        "bbox": tuple(block.get("bbox", (0.0, 0.0, 0.0, 0.0))),
                        "lines": block_lines,
                        "primary_font": _primary_font(block_fonts),
                        "structured": any("@" in line for line in block_lines)
                        or _is_heading_line(block_lines[0])
                        or _is_tabular_block(block_lines),
                    }
                )

            merged_blocks: list[dict] = []
            for block in raw_blocks:
                if merged_blocks and _can_merge_blocks(merged_blocks[-1], block):
                    merged_blocks[-1]["lines"].extend(block["lines"])
                    merged_blocks[-1]["bbox"] = (
                        merged_blocks[-1]["bbox"][0],
                        min(merged_blocks[-1]["bbox"][1], block["bbox"][1]),
                        max(merged_blocks[-1]["bbox"][2], block["bbox"][2]),
                        max(merged_blocks[-1]["bbox"][3], block["bbox"][3]),
                    )
                    continue

                merged_blocks.append(block)

            page_items: list[str] = []
            seen_items: set[str] = set()

            for block in merged_blocks:
                rendered_items = _render_block(block["lines"])
                for rendered in rendered_items:
                    dedupe_key = re.sub(r"\s+", " ", rendered).strip().lower()
                    if len(dedupe_key) > 20 and dedupe_key in seen_items:
                        continue
                    seen_items.add(dedupe_key)
                    page_items.append(rendered)

            merged_items = _merge_page_items(page_items)
            formatted_lines: list[str] = []
            for item in merged_items:
                for wrapped_line in _wrap_output_text(item):
                    formatted_lines.append(_normalize_text(wrapped_line))

            page_text = _compact_text_lines("\n".join(formatted_lines))
            pages.append(page_text)

        return pages, sorted(corrupt_fonts)
    finally:
        doc.close()


def _resolve_input_pdfs(input_path: str) -> list[str]:
    if os.path.isfile(input_path):
        if not input_path.lower().endswith(".pdf"):
            raise ValueError(f"Input file is not a PDF: {input_path}")
        return [input_path]

    pdf_files: list[str] = []
    for root, _, files in os.walk(input_path):
        for file in sorted(files):
            if file.lower().endswith(".pdf"):
                pdf_files.append(os.path.join(root, file))

    return sorted(pdf_files)


def _extract_metadata(pdf_path: str) -> str:
    """Ekstrak metadata dokumen menggunakan PyMuPDF (cepat, < 10 ms)."""
    try:
        doc = fitz.open(pdf_path)
        meta = doc.metadata or {}
        doc.close()
        fields = [
            ("Title", meta.get("title", "").strip()),
            ("Author", meta.get("author", "").strip()),
            ("Subject", meta.get("subject", "").strip()),
            ("Keywords", meta.get("keywords", "").strip()),
            ("Creator", meta.get("creator", "").strip()),
            ("Pages", meta.get("pages", "")),
        ]
        lines = [f"  {k:<10}: {v}" for k, v in fields if v and str(v) not in ("", "0")]
        return "\n".join(lines) if lines else "  (no metadata)"
    except Exception as e:
        return f"  (metadata error: {e})"


def extract_text_from_pdf(stream) -> str:
    """Extract plain text from a PDF file-like stream (for API use)."""
    # BUG FIX: Add size validation to prevent memory exhaustion
    MAX_PDF_SIZE = 50 * 1024 * 1024  # 50MB limit for PDF extraction

    data = stream.read() if hasattr(stream, "read") else stream

    if len(data) > MAX_PDF_SIZE:
        return f"[PDF too large for extraction: {len(data) // (1024*1024)}MB, limit is 50MB]"

    if len(data) == 0:
        return "[Empty PDF file]"

    try:
        doc = fitz.open(stream=data, filetype="pdf")
        texts = []
        for page in doc:
            texts.append(page.get_text("text"))
        doc.close()
        return "\n".join(texts)
    except Exception as e:
        return f"[PDF extraction error: {str(e)[:100]}]"


def extract_pdfs_from_directory(input_path, output_dir):
    """Extract each PDF into its own .txt file inside output_dir.

    Each file: output_dir / <original_pdf_stem>.txt

    Strategy:
        - PyMuPDF metadata for document info
        - PyMuPDF span-level extraction for text
        - Automatic filtering for corrupted font layers that create gibberish
    """
    os.makedirs(output_dir, exist_ok=True)

    pdf_files = _resolve_input_pdfs(input_path)

    print(f"Found {len(pdf_files)} PDF files in {input_path}")
    print(f"Output folder : {output_dir}")
    print("Using PyMuPDF metadata + filtered span extraction\n")

    total_start = time.time()

    for i, path in enumerate(pdf_files):
        filename = os.path.basename(path)
        stem = os.path.splitext(filename)[0]
        out_path = os.path.join(output_dir, stem + ".txt")

        print(f"[{i+1}/{len(pdf_files)}] {filename}")

        # --- metadata via PyMuPDF (fast) ---
        t0 = time.time()
        _extract_metadata(path)
        t_meta = time.time() - t0

        # --- text via filtered PyMuPDF spans ---
        try:
            t0 = time.time()
            pages_text, corrupt_fonts = _extract_filtered_text(path)
            t_text = time.time() - t0
            text_content = "\n".join(page for page in pages_text if page)
            chars = len(text_content)
            ignored = ", ".join(corrupt_fonts) if corrupt_fonts else "(none)"
            print(
                f"  meta: {t_meta*1000:.0f} ms | text: {t_text:.1f} s (fitz-filtered) | "
                f"{chars:,} chars | ignored fonts: {ignored} \u2192 {stem}.txt"
            )
        except Exception as e:
            pages_text = []
            corrupt_fonts = []
            text_content = f"[Error reading PDF text: {e}]\n"
            print(f"  -> ERROR: {e}")

        with open(out_path, "w", encoding="utf-8") as out:
            output_lines: list[str] = [f"####{filename}####"]

            for page_number, page_text in enumerate(pages_text or [text_content.strip()], start=1):
                total_pages = len(pages_text) if pages_text else 1
                output_lines.append(f"=={page_number}/{total_pages}==")
                if page_text.strip():
                    output_lines.extend(page_text.strip().splitlines())

            out.write("\n".join(output_lines).strip() + "\n")

    elapsed = time.time() - total_start
    print(f"\nFinished. Total time: {elapsed:.1f} s | {len(pdf_files)} files → {output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract each PDF into its own .txt file")
    parser.add_argument(
        "--input-dir",
        "-i",
        help="Input directory or a single PDF file to extract",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        help="Output directory for .txt files (default: <input>/referensiTXT)",
    )

    args = parser.parse_args()

    # Resolve input directory
    if args.input_dir:
        input_path = args.input_dir
    else:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        referensi_dir = os.path.join(current_dir, "referensi")
        if os.path.exists(referensi_dir):
            input_path = referensi_dir
        else:
            # BUG FIX: Removed hardcoded Windows path - use current directory instead
            input_path = os.path.join(current_dir, "referensi")

    # Resolve output directory
    if args.output_dir:
        output_dir = args.output_dir
    else:
        if os.path.isfile(input_path):
            output_dir = os.path.join(os.path.dirname(input_path), "referensiTXT")
        else:
            output_dir = os.path.join(input_path, "referensiTXT")

    extract_pdfs_from_directory(input_path, output_dir)
