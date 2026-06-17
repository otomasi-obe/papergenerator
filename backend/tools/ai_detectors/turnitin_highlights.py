#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Extract blue-highlighted text from Turnitin AI-detection PDF reports.

Key improvements over naive overlap detection:
  1. CENTER-POINT test  – a word is included only when its center (cx, cy)
     falls inside a blue rectangle, eliminating boundary words that merely
     overlap the edge of a highlight region.
  2. BLOCK-AWARE ordering – PyMuPDF assigns each text block a block_no.
     In a two-column page the left and right columns are separate blocks.
     We sort blocks by their topmost y-coordinate so they are output in
     visual reading order (top-to-bottom, left-to-right column by column)
     rather than interleaving words from both columns on the same visual row.
  3. NATURAL word order – within each block words are sorted by their
     (line_no, word_no) as returned by PyMuPDF, which exactly matches the
     PDF reading order.

Usage:
    python extract_highlights.py                    # all PDFs in same folder
    python extract_highlights.py path/to/file.pdf   # specific file
    python extract_highlights.py folder/            # all PDFs in folder
"""

import sys
import fitz                        # PyMuPDF  (pip install pymupdf)
from pathlib import Path
from collections import defaultdict

# ---------------------------------------------------------------------------
# Turnitin AI-highlight colour  (light teal / blue-green)
# ---------------------------------------------------------------------------
_HIGHLIGHT_RGB = (0.3203125, 0.77734375, 0.85546875)
_COLOR_TOL     = 0.02          # tolerance for floating-point colour comparison


def _is_highlight(fill: tuple | None) -> bool:
    """Return True when *fill* matches the Turnitin AI-highlight colour."""
    if not fill or len(fill) < 3:
        return False
    return all(abs(fill[i] - _HIGHLIGHT_RGB[i]) < _COLOR_TOL for i in range(3))


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------

def extract_page(page: fitz.Page) -> list[str]:
    """
    Return a list of highlighted text segments found on *page*.

    Each segment is a coherent run of highlighted words from one block
    (column).  Consecutive highlighted lines within a block are joined with
    a space; a gap caused by non-highlighted lines in the middle of a block
    produces separate segments.
    """
    # ---- Step 1: collect blue highlight rectangles -----------------------
    blue_rects: list[fitz.Rect] = [
        d["rect"]
        for d in page.get_drawings()
        if _is_highlight(d.get("fill"))
    ]
    if not blue_rects:
        return []

    # ---- Step 2: filter words by CENTER-POINT containment ---------------
    # word tuple: (x0, y0, x1, y1, text, block_no, line_no, word_no)
    highlighted: list[tuple] = []
    for w in page.get_text("words"):
        x0, y0, x1, y1 = w[0], w[1], w[2], w[3]
        text = w[4].strip()
        if not text:
            continue
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
        block_no, line_no, word_no = int(w[5]), int(w[6]), int(w[7])
        for rect in blue_rects:
            if rect.x0 <= cx <= rect.x1 and rect.y0 <= cy <= rect.y1:
                highlighted.append((block_no, line_no, word_no, y0, text))
                break   # no need to check further rects

    if not highlighted:
        return []

    # ---- Step 3: group by block_no ---------------------------------------
    block_words: dict[int, list] = defaultdict(list)
    for item in highlighted:
        block_words[item[0]].append(item)

    # Determine reading order of blocks by their minimum y position
    block_min_y = {
        b: min(w[3] for w in words)
        for b, words in block_words.items()
    }

    # ---- Step 4: assemble text in natural order within each block --------
    segments: list[str] = []

    for blk in sorted(block_words, key=lambda b: block_min_y[b]):
        # Sort words by (line_no, word_no) — the PDF's own reading order
        words_sorted = sorted(block_words[blk], key=lambda w: (w[1], w[2]))

        # Group words into lines
        lines_dict: dict[int, list[str]] = defaultdict(list)
        for item in words_sorted:
            lines_dict[item[1]].append((item[2], item[4]))   # (word_no, text)

        sorted_line_nos = sorted(lines_dict)

        # Build per-line strings
        line_texts  = []
        line_nos_in = []
        for ln in sorted_line_nos:
            # Sort words within the line by word_no
            words_in_line = sorted(lines_dict[ln], key=lambda x: x[0])
            line_texts.append(" ".join(w[1] for w in words_in_line))
            line_nos_in.append(ln)

        # Group *consecutive* highlighted line-nos into one segment.
        # A gap (e.g. a non-highlighted line in the middle) splits segments.
        current: list[str] = [line_texts[0]]
        for i in range(1, len(line_nos_in)):
            gap = line_nos_in[i] - line_nos_in[i - 1]
            if gap <= 1:                    # consecutive (or same) line
                current.append(line_texts[i])
            else:                            # non-highlighted gap → new segment
                segments.append(" ".join(current))
                current = [line_texts[i]]
        segments.append(" ".join(current))

    return segments


def extract_pdf(pdf_path: Path) -> str:
    """Return a formatted string of all highlighted passages in *pdf_path*."""
    doc = fitz.open(str(pdf_path))
    out: list[str] = []

    for pg_num in range(doc.page_count):
        segments = extract_page(doc[pg_num])
        if not segments:
            continue

        out.append(f"=== Page {pg_num + 1} ===")
        for seg in segments:
            out.append(seg)
        out.append("")          # blank line between pages

    doc.close()
    return "\n".join(out)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _collect_pdfs(arg: str) -> list[Path]:
    p = Path(arg)
    if p.is_dir():
        return sorted(p.glob("*.pdf"))
    if p.is_file() and p.suffix.lower() == ".pdf":
        return [p]
    return []


def main() -> None:
    if len(sys.argv) > 1:
        pdf_files: list[Path] = []
        for arg in sys.argv[1:]:
            pdf_files.extend(_collect_pdfs(arg))
    else:
        # default: all PDFs in the same folder as this script
        pdf_files = sorted(Path(__file__).parent.glob("*.pdf"))

    if not pdf_files:
        print("No PDF files found.")
        sys.exit(1)

    for pdf_path in pdf_files:
        print(f"\n{'='*60}")
        print(f"File : {pdf_path.name}")
        print(f"{'='*60}")

        text = extract_pdf(pdf_path)
        if text.strip():
            print(text)
        else:
            print("(no highlighted text found)")

        out_path = pdf_path.with_name(pdf_path.stem + "_highlights.txt")
        out_path.write_text(text, encoding="utf-8")
        print(f"\n[Saved → {out_path.name}]")


if __name__ == "__main__":
    main()
