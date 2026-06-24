"""
Fix script: Sync PaperImage ke figures array dan re-distribute ke content.

Masalah: 73/88 paper punya gambar di PaperImage DB tapi figures array kosong,
sehingga gambar tidak muncul di editor/preview.

Solusi:
1. Load PaperImage dari DB untuk setiap paper
2. Update figures array dengan Path yang valid (dari PaperImage.filename)
3. Call _distribute_figures_to_sections untuk add gambar ke content
4. Save kembali ke DB
"""

import json
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from main import app
from database.models import Paper, PaperImage, db
from sqlalchemy.orm.attributes import flag_modified


def fix_paper_images(paper_id=None, dry_run=False):
    """Fix paper images by syncing PaperImage to figures array and distributing to content."""
    
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
                
            images = PaperImage.query.filter_by(paper_id=p.id).order_by(PaperImage.created_at).all()
            if not images:
                continue
            
            data = p.data
            if isinstance(data, str):
                data = json.loads(data)
            
            figures = data.get('figures', [])
            
            # Check if figures array has valid Path
            has_valid = any(f.get('Path') or f.get('path') or f.get('filename') for f in figures)
            
            if has_valid:
                continue  # Already has valid figures, skip
            
            # Sync PaperImage to figures array
            print(f"Fixing paper {p.id}: {p.title[:50]}... ({len(images)} images)")
            
            # If figures array is smaller than images, extend it
            while len(figures) < len(images):
                figures.append({})
            
            # Update figures with PaperImage data
            for i, img in enumerate(images):
                if i >= len(figures):
                    figures.append({})
                
                fig = figures[i]
                # Set Path to filename (backend serves from /api/images/<paper_id>/<filename>)
                if not fig.get('Path') and not fig.get('path'):
                    fig['Path'] = img.filename
                
                # Set filename if not set
                if not fig.get('filename'):
                    fig['filename'] = img.filename
                
                # Set caption from original_name if not set
                if not fig.get('caption') and img.original_name:
                    fig['caption'] = img.original_name
            
            data['figures'] = figures
            
            # Distribute figures to sections (import from main)
            from main import _distribute_figures_to_sections
            _distribute_figures_to_sections(data)
            
            if dry_run:
                print(f"  [DRY RUN] Would update {len(images)} figures")
            else:
                # IMPORTANT: flag_modified is required for JSON/JSONB columns
                # SQLAlchemy doesn't detect changes to mutable dict objects
                p.data = data
                flag_modified(p, 'data')
                db.session.commit()
                print(f"  Updated {len(images)} figures")
                fixed_count += 1
        
        print(f"\nFixed {fixed_count} papers")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Fix paper images")
    parser.add_argument("--paper-id", help="Fix specific paper ID")
    parser.add_argument("--dry-run", action="store_true", help="Dry run without saving")
    args = parser.parse_args()
    
    fix_paper_images(paper_id=args.paper_id, dry_run=args.dry_run)
