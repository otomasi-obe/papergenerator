"""
Reconcile paper figures with actual generated images.

During generation, figures have placeholder paths like "gambar/fig1.png".
After image generation, actual images are stored in data/uploads/{paper_id}/{uuid}.jpg.
This module maps figures to their actual image files before DOCX export.
"""

import os
from pathlib import Path
from typing import Optional
import logging

log = logging.getLogger(__name__)


def reconcile_figure_images(paper_id: str, paper_data: dict, upload_base: Path) -> None:
    """
    Update figure Path fields to point to actual generated images.
    
    Args:
        paper_id: Paper ID
        paper_data: Paper data dict (modified in place)
        upload_base: Base upload folder (e.g., backend/data/uploads)
    """
    if not paper_id:
        log.warning("[reconcile] No paper_id provided")
        return
        
    figures = paper_data.get("figures", [])
    if not figures:
        log.debug("[reconcile] No figures in paper data")
        return
    
    log.info("[reconcile] Paper %s has %d figures", paper_id, len(figures))
    
    # Find all images in the paper's upload folder
    paper_upload_dir = upload_base / paper_id
    log.info("[reconcile] Looking for images in %s", paper_upload_dir)
    
    if not paper_upload_dir.exists():
        log.warning("[reconcile] No upload folder for paper %s at %s", paper_id, paper_upload_dir)
        return
    
    # Get all image files in the folder
    image_files = []
    for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
        image_files.extend(paper_upload_dir.glob(f'*{ext}'))
    
    if not image_files:
        log.debug("No images found for paper %s", paper_id)
        return
    
    # Sort by modification time (oldest first = likely fig1, fig2, etc.)
    image_files.sort(key=lambda f: f.stat().st_mtime)
    
    log.info("Found %d images for paper %s", len(image_files), paper_id)
    
    # Map figures to images
    # Strategy: match by order (fig1 -> first image, fig2 -> second image, etc.)
    # Also try to match by figure number in Path field
    
    used_images = set()
    
    for fig in figures:
        if not isinstance(fig, dict):
            continue
            
        # Skip if already has absolute path to existing file
        current_path = str(fig.get("Path") or fig.get("path") or "").strip()
        if not current_path or (os.path.isabs(current_path) and os.path.exists(current_path)):
            continue
        
        # Try to find matching image by number
        fig_num = _extract_figure_number(current_path, fig.get("Title", ""))
        matched = None
        
        # Strategy 1: Match by figure number (fig1 -> 1st image, fig2 -> 2nd, etc.)
        if fig_num and fig_num <= len(image_files):
            candidate = image_files[fig_num - 1]
            if str(candidate) not in used_images:
                matched = candidate
        
        # Strategy 2: Use next available unused image
        if not matched:
            for img in image_files:
                if str(img) not in used_images:
                    matched = img
                    break
        
        if matched:
            # Update Path to ABSOLUTE path (builders prepend BASE to relative paths)
            fig["Path"] = str(matched.resolve())
            used_images.add(str(matched))
            log.debug("Mapped figure to %s", matched.name)
    
    log.info("Reconciled %d/%d figures for paper %s", len(used_images), len(figures), paper_id)


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
