"""
Fix script: Normalize gambar paths in paper data to match PaperImage filenames.

Root cause: Gambar items in section content have corrupted paths with spaces
(e.g., 'system_a rchitecture.jpg' instead of 'system_architecture.jpg') and
full filesystem paths instead of just filenames.

Solution: For each gambar item, find the matching PaperImage by fuzzy filename
match and update the Path to the correct filename.
"""

import json
import os
import sys
import re
from pathlib import Path
from difflib import SequenceMatcher

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from main import app
from database.models import Paper, PaperImage, db
from sqlalchemy.orm.attributes import flag_modified


def normalize_filename(path):
    """Extract basename and remove spaces to get a normalized filename."""
    if not path:
        return None
    # Get basename
    basename = os.path.basename(path)
    # Remove spaces (they were accidentally inserted)
    normalized = basename.replace(' ', '')
    return normalized


def find_matching_image(normalized_name, available_filenames):
    """Find best matching filename from available PaperImage filenames."""
    # Exact match
    if normalized_name in available_filenames:
        return normalized_name
    
    # Try removing spaces from available filenames too
    for fname in available_filenames:
        if fname.replace(' ', '') == normalized_name:
            return fname
    
    # Fuzzy match (for cases like 'system_a rchitecture' -> 'system_architecture')
    best_match = None
    best_score = 0
    for fname in available_filenames:
        score = SequenceMatcher(None, normalized_name, fname).ratio()
        if score > best_score and score > 0.8:  # 80% similarity threshold
            best_score = score
            best_match = fname
    
    return best_match


def fix_paper_image_paths(paper_id=None, dry_run=False):
    """Fix gambar paths in paper data by normalizing and matching to PaperImage."""
    
    with app.app_context():
        if paper_id:
            papers = [Paper.query.filter_by(id=paper_id).first()]
            if not papers[0]:
                print(f"Paper {paper_id} not found")
                return
        else:
            papers = Paper.query.all()
        
        fixed_count = 0
        
        for p in papers:
            if not p:
                continue
                
            images = PaperImage.query.filter_by(paper_id=p.id).all()
            if not images:
                continue
            
            available_filenames = {img.filename for img in images}
            
            data = p.data
            if isinstance(data, str):
                data = json.loads(data)
            
            # Find all gambar items recursively
            gambar_items = []
            
            def find_gambar(obj):
                if isinstance(obj, dict):
                    if obj.get('id') == 'gambar':
                        gambar_items.append(obj)
                    for v in obj.values():
                        find_gambar(v)
                elif isinstance(obj, list):
                    for item in obj:
                        find_gambar(item)
            
            find_gambar(data)
            
            if not gambar_items:
                continue
            
            # Check if any gambar has malformed path (full path or spaces)
            needs_fix = False
            for item in gambar_items:
                path = item.get('Path') or item.get('path')
                if path:
                    # Needs fix if: contains full path, or has spaces, or doesn't match available
                    if '/' in path or ' ' in path or path not in available_filenames:
                        needs_fix = True
                        break
            
            if not needs_fix:
                continue
            
            print(f"Fixing paper {p.id}: {p.title[:50]}... ({len(gambar_items)} gambar items)")
            
            # Fix paths
            for item in gambar_items:
                path = item.get('Path') or item.get('path')
                if not path:
                    continue
                
                normalized = normalize_filename(path)
                matched = find_matching_image(normalized, available_filenames)
                
                if matched:
                    if dry_run:
                        print(f"  [DRY RUN] Would change: {path} -> {matched}")
                    else:
                        item['Path'] = matched
                        print(f"  Fixed: {path} -> {matched}")
                else:
                    print(f"  [WARNING] No match for: {path} (normalized: {normalized})")
            
            if not dry_run:
                p.data = data
                flag_modified(p, 'data')
                db.session.commit()
                fixed_count += 1
        
        print(f"\nFixed {fixed_count} papers")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Fix paper image paths")
    parser.add_argument("--paper-id", help="Fix specific paper ID")
    parser.add_argument("--dry-run", action="store_true", help="Dry run without saving")
    args = parser.parse_args()
    
    fix_paper_image_paths(paper_id=args.paper_id, dry_run=args.dry_run)
