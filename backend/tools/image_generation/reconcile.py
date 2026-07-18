"""
Reconcile paper figures with actual generated images.

During generation, figures have placeholder paths like "gambar/fig1.png".
After image generation, actual images are stored in user/<username>/<paper_id>/image/
(via ``safe_paper_dir``).
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
        upload_base: Base upload folder (e.g., backend/user/<user_id>/uploads) — used as fallback
    """
    if not paper_id:
        log.warning("[reconcile] No paper_id provided")
        return

    # ── Collect all image files for this paper ──────────────────────────
    # Scan ALL dirs (canonical + legacy) and merge file lists
    all_dirs = _find_paper_image_dirs(paper_id, upload_base)
    log.info("[reconcile] Paper %s — image dirs: %s", paper_id, [str(d) for d in all_dirs])

    if not all_dirs:
        log.warning("[reconcile] No image folder for paper %s", paper_id)
        return

    image_files: List[Path] = []
    seen_names: set[str] = set()
    for img_dir in all_dirs:
        for ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
            for f in img_dir.glob(f'*{ext}'):
                if f.name not in seen_names:
                    image_files.append(f)
                    seen_names.add(f.name)
            for f in img_dir.glob(f'*{ext.upper()}'):
                if f.name not in seen_names:
                    image_files.append(f)
                    seen_names.add(f.name)

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
            # Normalise absolute paths to basename
            if current_path and os.path.isabs(current_path):
                base = os.path.basename(current_path).replace(" ", "")
                fig["Path"] = base
                if os.path.exists(current_path) or base in file_map:
                    used_images.add(base)
                    continue  # already resolved

            matched = _match_image(current_path, fig.get("Title", ""), file_map, used_images, image_files)
            if matched:
                fig["Path"] = matched.name  # basename only
                used_images.add(matched.name)

    # ── 2. Patch section content gambar items ───────────────────────────
    content_fig_count = _patch_section_gambar_paths(paper_data, file_map)
    
    log.info(
        "[reconcile] Done for paper %s — %d legacy figures, %d content gambar patched",
        paper_id,
        len(figures),
        content_fig_count,
    )


def _normalise_filename(fname: str) -> str:
    """Remove stray spaces inside a filename.

    AI models sometimes emit paths like ``system_a rchitecture.png`` or
    ``error_v s_f req.png`` — spaces inserted mid-token (likely a tokeniser
    artifact). Disk files are ``system_architecture.jpg`` etc.
    Stripping all spaces makes matching robust.
    """
    if not fname:
        return fname
    return fname.replace(" ", "")


def _normalised_stem_match(
    stem: str,
    file_map: dict[str, Path],
    used_images: set[str],
) -> Optional[Path]:
    """Match a stem against file_map keys, ignoring spaces and extension.

    Tries (in order):
      1. Exact stem match (extension-agnostic)
      2. Stem match with spaces removed from BOTH sides
      3. Stem match ignoring underscores vs hyphens
    """
    if not stem:
        return None
    stem_norm = _normalise_filename(stem).lower()
    # Build a normalised stem → Path index once
    for fkey, fpath in file_map.items():
        if fpath.name in used_images:
            continue
        fkey_stem = os.path.splitext(fkey)[0]
        if fkey_stem == stem:
            return fpath
        if _normalise_filename(fkey_stem).lower() == stem_norm:
            return fpath
        # Also try underscore/hyphen equivalence
        fkey_stem_norm = fkey_stem.replace("-", "_").lower()
        stem_norm_uh = stem_norm.replace("-", "_")
        if fkey_stem_norm == stem_norm_uh:
            return fpath
    return None


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

    # Strategy 0a: normalised filename match (strip stray spaces)
    if fname:
        fname_norm = _normalise_filename(fname)
        if fname_norm != fname and fname_norm in file_map and fname_norm not in used_images:
            return file_map[fname_norm]

    # Strategy 0b: extension-agnostic stem match (JSON says .png, Gemini saved .jpg)
    if fname:
        stem = os.path.splitext(fname)[0]
        matched = _normalised_stem_match(stem, file_map, used_images)
        if matched:
            return matched

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

    Handles nested structures: paper_data.paper.section2, paper_data.section1, etc.
    Walks recursively into any dict that contains section* keys.

    Returns the number of gambar items patched.
    """
    patched = 0

    def _walk(obj: dict) -> None:
        nonlocal patched
        if not isinstance(obj, dict):
            return

        # Check if this dict itself has section* keys
        section_keys = [k for k in obj if isinstance(k, str) and re.match(r'^section\d+[a-z]?$', k)]
        if section_keys:
            for key in section_keys:
                section = obj.get(key)
                if not isinstance(section, dict):
                    continue
                content = section.get("content")
                if isinstance(content, list):
                    patched += _patch_content_list(content, file_map)
                # Also check subsection keys like section2a, section3b inside a section
                for sub_key, sub in section.items():
                    if sub_key in ("content", "title", "number", "letter"):
                        continue
                    if isinstance(sub, dict) and re.match(r'^section\d+[a-z]+$', sub_key):
                        sub_content = sub.get("content")
                        if isinstance(sub_content, list):
                            patched += _patch_content_list(sub_content, file_map)

        # Also handle legacy "sections" array format
        for section in obj.get("sections", []):
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

        # Recurse into nested dicts that might wrap the paper (e.g. paper_data.paper)
        for key, val in obj.items():
            if key in ("sections", "subsections", "content", "title"):
                continue
            if isinstance(val, dict):
                _walk(val)

    _walk(paper_data)
    return patched


def _patch_content_list(content: list, file_map: dict[str, Path]) -> int:
    """Patch gambar items in a content list. Returns count patched.

    All resolved paths are stored as **basename only** (e.g. ``fig1.jpg``),
    never absolute server paths.  The frontend builds the API URL from the
    basename + paper_id; journal DOCX generators already call
    ``os.path.basename()`` before resolving on disk, so basename is safe.
    """
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
                        item["Path"] = fpath.name  # basename only
                        patched += 1
                        log.debug("[reconcile] Patched content gambar via ImageNumber %s: → %s", img_num, item["Path"])
                        break
            continue

        # ── Skip if user already set a valid bare filename ──
        # Don't override user's manual image selection
        if not os.path.isabs(path_text):
            base = os.path.basename(path_text).replace(" ", "")
            if base in file_map:
                # Already a valid filename — keep it, just mark as patched
                item["Path"] = base
                patched += 1
                continue

        # Normalise existing absolute paths to basename even if file exists.
        # Frontend only needs the filename; serving uses paper_id to locate.
        if os.path.isabs(path_text):
            fname = os.path.basename(path_text)
            if fname:
                # Normalise: remove spaces AI models insert mid-token
                normalised = fname.replace(" ", "")
                if normalised in file_map:
                    item["Path"] = normalised
                    patched += 1
                    log.debug("[reconcile] Abs path → basename: %s → %s", fname, item["Path"])
                    continue
                # Also try stem match with spaces removed
                stem = os.path.splitext(normalised)[0]
                for fkey, fpath in file_map.items():
                    if os.path.splitext(fkey)[0] == stem:
                        item["Path"] = fpath.name
                        patched += 1
                        log.debug("[reconcile] Abs path stem-matched: %s → %s", fname, item["Path"])
                        break
                else:
                    # File not in file_map but normalise to basename anyway
                    item["Path"] = normalised
                    patched += 1
                    log.debug("[reconcile] Abs path stripped to basename: %s → %s", path_text, item["Path"])
                continue

        # Try to resolve the bare filename against the upload folder.
        # AI models sometimes insert stray spaces inside filenames
        # (e.g. "system_a rchitecture.png" instead of "system_architecture.png");
        # normalise them before matching.
        fname = os.path.basename(path_text)
        if fname:
            # Extension-aware lookup: JSON may say .png but actual file is .jpg (Gemini output)
            stem = os.path.splitext(fname)[0]
            matched_path = None
            if fname in file_map:
                matched_path = file_map[fname]
            elif stem:
                # Try stem match with any extension (e.g. fig1.png → fig1.jpg),
                # including normalised (spaces removed) stem match.
                matched_path = _normalised_stem_match(stem, file_map, set())
            if matched_path:
                item["Path"] = matched_path.name  # basename only
                patched += 1
                log.debug("[reconcile] Patched content gambar: %s → %s", fname, item["Path"])
                continue

        # Also try ImageNumber-based matching as fallback
        img_num = item.get("ImageNumber") or item.get("imageNumber")
        if img_num:
            for fname_cand, fpath in file_map.items():
                num_in_name = re.search(r'(\d+)', fname_cand)
                if num_in_name and num_in_name.group(1) == str(img_num):
                    item["Path"] = fpath.name  # basename only
                    patched += 1
                    log.debug("[reconcile] Patched content gambar via ImageNumber %s: → %s", img_num, item["Path"])
                    break

    return patched


def _find_paper_image_dirs(paper_id: str, upload_base: Path) -> list[Path]:
    """Return ALL image directories for this paper (canonical + legacy).

    Priority:
      1. user/<username>/<paper_id>/image/  (canonical, per-user)
      2. user/<paper_id>/image/              (canonical, direct)
      3. upload_base/<paper_id>/             (legacy fallback)
    """
    dirs = []

    # 1. user/<paper_id>/image/ (canonical)
    from utils.database.models import Paper
    from main import app
    try:
        with app.app_context():
            paper = Paper.query.get(paper_id)
            if paper and paper.user_id:
                from utils.core.user_storage import get_username
                username = get_username(user_id=paper.user_id)
                if username:
                    user_dir = Path(__file__).resolve().parent.parent.parent / "user" / username / paper_id / "image"
                    if user_dir.exists():
                        dirs.append(user_dir)
    except Exception:
        pass

    # 2. user/<paper_id>/image/ (direct canonical)
    direct = Path(__file__).resolve().parent.parent.parent / "user" / paper_id / "image"
    if direct.exists():
        dirs.append(direct)

    # 3. Scan all user dirs for paper_id/image/
    try:
        user_root = Path(__file__).resolve().parent.parent.parent / "user"
        for user_dir in user_root.iterdir():
            if not user_dir.is_dir() or user_dir.name.startswith("."):
                continue
            candidate = user_dir / paper_id / "image"
            if candidate.exists() and candidate not in dirs:
                dirs.append(candidate)
    except Exception:
        pass

    # Fallback: upload_base/<paper_id>/
    legacy = upload_base / paper_id
    if legacy.exists() and legacy not in dirs:
        dirs.append(legacy)

    return dirs


def _find_paper_image_dir(paper_id: str, upload_base: Path) -> Optional[Path]:
    """Legacy wrapper — returns first existing dir."""
    dirs = _find_paper_image_dirs(paper_id, upload_base)
    return dirs[0] if dirs else None


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
