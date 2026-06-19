#!/usr/bin/env python3
"""Batch generate Kelompok 1 journals using paper data from DB.
Uses the web backend's _get_builder_for_journal() + adapter mechanism.
"""
import sys, json, os, uuid, re
from pathlib import Path
sys.path.insert(0, "/home/sirobo/papergenerator/backend")

OUTPUT_DIR = Path("/home/sirobo/ANNABIL/Project Papergenerator_Annabil/A transit output web")
JOURNAL_DIR = Path("/home/sirobo/papergenerator/backend/tools/Journal")
USER_BASE = Path("/home/sirobo/papergenerator/backend/user")

KELOMPOK1 = ["AEJ","AMORI","DJLIT","EASR","ELCTRICES","ELKOLIND","ENERGIUPM",
             "El-Usrah","ICET","ICIMECE","ICONIE","ICOSEG","IJB","IJECE",
             "IJEECS","IJIMS","IJITEE","IJRED"]

def main():
    from main import app, _get_builder_for_journal
    with app.app_context():
        from database.models import Paper
        
        # Find paper with richest content (most figures)
        papers = Paper.query.filter(Paper.data.isnot(None)).all()
        best_paper = None
        best_score = -1
        for p in papers:
            if not p.data: continue
            d = p.data
            figs = len(d.get("figures", []))
            # Also check sections for embedded gambar
            for sk in ["section1","section2","section3","section4","section5"]:
                s = d.get(sk, {})
                c = s.get("content", [])
                if isinstance(c, list):
                    for item in c:
                        if isinstance(item, dict) and item.get("id") in ("gambar","image"):
                            figs += 1
            refs = len(d.get("references", []))
            score = figs + refs
            if score > best_score:
                best_score = score
                best_paper = p
        
        if not best_paper:
            print("No paper found!")
            return
        
        paper_data = best_paper.data
        print(f"Using paper: id={best_paper.id}, title={paper_data.get('title','?')[:60]}, figures={len(paper_data.get('figures',[]))}")
        
        # Also count embedded gambar
        emb_gambar = 0
        for sk in ["section1","section2","section3","section4","section5"]:
            s = paper_data.get(sk, {})
            c = s.get("content", [])
            if isinstance(c, list):
                for item in c:
                    if isinstance(item, dict) and item.get("id") in ("gambar","image"):
                        emb_gambar += 1
        print(f"Embedded gambar: {emb_gambar}")
        
        results = []
        for journal in KELOMPOK1:
            # Set journal in paper data
            paper_data["journal"] = journal
            
            # Write temp JSON file
            temp_dir = USER_BASE / "batch_test" / "export"
            temp_dir.mkdir(parents=True, exist_ok=True)
            json_path = temp_dir / f"_tmp_{journal}_{uuid.uuid4().hex[:6]}.json"
            json_path.write_text(json.dumps(paper_data, ensure_ascii=False, indent=2), encoding="utf-8")
            
            # Output path
            safe_title = re.sub(r"[^a-zA-Z0-9_\-.]+", "_", str(paper_data.get("title", "paper"))).strip("_")[:40]
            out_path = OUTPUT_DIR / f"{journal}_{safe_title}.docx"
            
            try:
                # Get builder via web backend mechanism
                canonical, builder = _get_builder_for_journal(journal)
                
                # Generate
                builder(str(json_path), str(out_path))
                
                # Verify output exists
                if out_path.exists() and out_path.stat().st_size > 1000:
                    size_kb = out_path.stat().st_size / 1024
                    results.append((journal, f"OK ({size_kb:.0f}KB)"))
                    print(f"  {journal}: OK -> {out_path.name} ({size_kb:.0f}KB)")
                else:
                    results.append((journal, "FAIL (empty/small)"))
                    print(f"  {journal}: FAIL - output too small")
            except Exception as e:
                results.append((journal, f"FAIL: {str(e)[:80]}"))
                print(f"  {journal}: FAILED - {e}")
            
            # Cleanup temp JSON
            try: json_path.unlink(missing_ok=True)
            except: pass
        
        print("\n=== RESULTS ===")
        for j, r in results:
            print(f"{j:12s} | {r}")

if __name__ == "__main__":
    main()
