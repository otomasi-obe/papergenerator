"""
Reconcile paper figures with actual generated images.

During generation, figures have placeholder paths like "gambar/fig1.png".
After image generation, actual images are stored in user/<username>/<paper_id>/image/
(via ``safe_paper_dir``), or legacy ``data/uploads/<paper_id>/``.
This module maps figures to their actual image files before DOCX export.

Two data shapes carry image paths:
  1. ``paper_data["figures"]``  — legacy flat array (used by some generators)
  2. ``section*.content[]`` items with ``id: "gambar"`` — the content-block
     format consumed by IEEEgen and friends.

Both are patched here so the exporter always finds real files.
"""

import os
import re
from pathlib import Path
from typing import Optional, List
import logging

log = logging.getLogger(__name__)


def reconcile_figure_images(paper_id: str, paper_data: dict, upload_base: Path) -> None:
    """
    Update figure Path fields to point to actual generated images.
    
    Args:
        paper_id: Paper ID
        paper_data: Paper data dict (modified in place)
        upload_base: Base upload folder (e.g., backend/data/uploads) — used as fallback
    """
    if not paper_id:
        log.warning("[reconcile] No paper_id provided")
        return

    # ── Collect all image files for this paper ──────────────────────────
    # Primary: user/<username>/<paper_id>/image/ (via safe_paper_dir)
    # Fallback: data/uploads/<paper_id>/
    paper_upload_dir = _find_paper_image_dir(paper_id, upload_base)
    log.info("[reconcile] Paper %s — using image dir: %s", paper_id, paper_upload_dir)

    if paper_upload_dir is None or not paper_upload_dir.exists():
        log.warning("[reconcile] No image folder for paper %s", paper_id)
        return

    image_files: List[Path] = []
    for ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
        image_files.extend(paper_upload_dir.glob(f'*{ext}'))

    if not image_files:
        log.debug("[reconcile] No images found for paper %s", paper_id)
        return

    # Sort by modification time (oldest first = likely fig1, fig2, etc.)
    image_files.sort(key=lambda f: f.stat().st_mtime)
    log.info("[reconcile] Found %d images for paper %s", len(image_files), paper_id)

    # Build a filename → absolute-path lookup for O(1) matching
    file_map: dict[str, Path] = {f.name: f for f in image_files}

    # ── 1. Patch legacy figures[] array ─────────────────────────────────
    figures = paper_data.get("figures", [])
    if figures:
        log.info("[reconcile] Patching %d legacy figures[]", len(figures))
        used_images: set[str] = set()
        for fig in figures:
            if not isinstance(fig, dict):
                continue
            current_path = str(fig.get("Path") or fig.get("path") or "").strip()
            if current_path and os.path.isabs(current_path) and os.path.exists(current_path):
                continue  # already absolute & valid

            matched = _match_image(current_path, fig.get("Title", ""), file_map, used_images, image_files)
            if matched:
                fig["Path"] = str(matched.resolve())
                used_images.add(matched.name)

    # ── 2. Patch section content gambar items ───────────────────────────
    content_fig_count = _patch_section_gambar_paths(paper_data, file_map)
    
    log.info(
        "[reconcile] Done for paper %s — %d legacy figures, %d content gambar patched",
        paper_id,
        len(figures),
        content_fig_count,
    )


def _match_image(
    current_path: str,
    title: str,
    file_map: dict[str, Path],
    used_images: set[str],
    image_files: List[Path],
) -> Optional[Path]:
    """Find the best matching image file for a figure entry."""

    # Strategy 0: direct filename match (e.g. Path = "abc123.jpg")
    fname = os.path.basename(current_path) if current_path else ""
    if fname and fname in file_map and fname not in used_images:
        return file_map[fname]

    # Strategy 0b: extension-agnostic stem match (JSON says .png, Gemini saved .jpg)
    if fname:
        stem = os.path.splitext(fname)[0]
        if stem:
            for fkey, fpath in file_map.items():
                if os.path.splitext(fkey)[0] == stem and fkey not in used_images:
                    return fpath

    # Strategy 1: match by figure number
    fig_num = _extract_figure_number(current_path, title)
    if fig_num and fig_num <= len(image_files):
        candidate = image_files[fig_num - 1]
        if candidate.name not in used_images:
            return candidate

    # Strategy 2: next unused image
    for img in image_files:
        if img.name not in used_images:
            return img

    return None


def _patch_section_gambar_paths(paper_data: dict, file_map: dict[str, Path]) -> int:
    """
    Walk all section/subsection content arrays and patch ``gambar`` items
    whose ``Path`` is a bare filename → absolute path from the upload folder.

    Returns the number of gambar items patched.
    """
    patched = 0

    for key, section in paper_data.items():
        if not isinstance(section, dict):
            continue
        # Match section keys: section1, section2a, section3b, etc.
        if not re.match(r'^section\d+[a-z]?$', key):
            continue

        content = section.get("content")
        if isinstance(content, list):
            patched += _patch_content_list(content, file_map)

        # Also check subsection keys like section2a, section3b inside a section
        for sub_key, sub in section.items():
            if sub_key == "content" or sub_key == "title" or sub_key == "number" or sub_key == "letter":
                continue
            if isinstance(sub, dict) and re.match(r'^section\d+[a-z]+$', sub_key):
                sub_content = sub.get("content")
                if isinstance(sub_content, list):
                    patched += _patch_content_list(sub_content, file_map)

    # Also handle legacy "sections" array format
    for section in paper_data.get("sections", []):
        if not isinstance(section, dict):
            continue
        content = section.get("content")
        if isinstance(content, list):
            patched += _patch_content_list(content, file_map)
        for sub in section.get("subsections", []):
            if isinstance(sub, dict):
                sub_content = sub.get("content")
                if isinstance(sub_content, list):
                    patched += _patch_content_list(sub_content, file_map)

    return patched


def _patch_content_list(content: list, file_map: dict[str, Path]) -> int:
    """Patch gambar items in a content list. Returns count patched."""
    patched = 0
    for item in content:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id", "")).lower()
        if item_id not in ("gambar", "image"):
            continue

        path_text = str(item.get("Path", "")).strip()
        if not path_text:
            # Fall through to ImageNumber matching instead of skipping
            img_num = item.get("ImageNumber") or item.get("imageNumber")
            if img_num:
                for fname, fpath in file_map.items():
                    num_in_name = re.search(r'(\d+)', fname)
                    if num_in_name and num_in_name.group(1) == str(img_num):
                        item["Path"] = str(fpath.resolve())
                        patched += 1
                        log.debug("[reconcile] Patched content gambar via ImageNumber %s: → %s", img_num, item["Path"])
                        break
            continue

        # Skip if already absolute and exists
        if os.path.isabs(path_text) and os.path.exists(path_text):
            continue

        # Try to resolve the bare filename against the upload folder
        fname = os.path.basename(path_text)
        if fname:
            # Extension-aware lookup: JSON may say .png but actual file is .jpg (Gemini output)
            stem = os.path.splitext(fname)[0]
            matched_path = None
            if fname in file_map:
                matched_path = file_map[fname]
            elif stem:
                # Try stem match with any extension (e.g. fig1.png → fig1.jpg)
                for fkey, fpath in file_map.items():
                    if os.path.splitext(fkey)[0] == stem:
                        matched_path = fpath
                        break
            if matched_path:
                item["Path"] = str(matched_path.resolve())
                patched += 1
                log.debug("[reconcile] Patched content gambar: %s → %s", fname, item["Path"])
                continue

        # Also try ImageNumber-based matching as fallback
        img_num = item.get("ImageNumber") or item.get("imageNumber")
        if img_num:
            for fname_cand, fpath in file_map.items():
                num_in_name = re.search(r'(\d+)', fname_cand)
                if num_in_name and num_in_name.group(1) == str(img_num):
                    item["Path"] = str(fpath.resolve())
                    patched += 1
                    log.debug("[reconcile] Patched content gambar via ImageNumber %s: → %s", img_num, item["Path"])
                    break

    return patched


def _find_paper_image_dir(paper_id: str, upload_base: Path) -> Optional[Path]:
    """
    Locate the image directory for a paper.
    Returns the first existing path:
      1. user/<username>/<paper_id>/image/   (via safe_paper_dir)
      2. data/uploads/<paper_id>/            (legacy)
    """
    # Primary: safe_paper_image_dir (user/<username>/<paper_id>/image/)
    try:
        from tools.editor.utils import safe_paper_image_dir
        image_dir = safe_paper_image_dir(paper_id)
        if image_dir and image_dir.exists():
            return image_dir
    except Exception:
        log.debug("[reconcile] safe_paper_image_dir lookup failed", exc_info=True)

    # Fallback: legacy data/uploads/<paper_id>/
    legacy_dir = upload_base / paper_id
    if legacy_dir.exists():
        return legacy_dir

    return None


def _extract_figure_number(path: str, title: str) -> Optional[int]:
    """
    Extract figure number from path or title.
    
    Args:
        path: Figure path like "gambar/fig1.png"
        title: Figure title like "Figure 1: ..."
    
    Returns:
        Figure number or None
    """
    import re
    
    # Try path first: "gambar/fig1.png" -> 1
    path_match = re.search(r'fig(\d+)', path.lower())
    if path_match:
        return int(path_match.group(1))
    
    # Try title: "Figure 1: ..." -> 1
    title_match = re.search(r'figure\s+(\d+)', title.lower())
    if title_match:
        return int(title_match.group(1))
    
    return None
