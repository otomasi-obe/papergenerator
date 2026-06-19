#!/usr/bin/env python3
"""Batch generate Kelompok 1 using user folder paper.json (has inline gambar).
"""
import sys, json, os, uuid, re, shutil
from pathlib import Path
sys.path.insert(0, "/home/sirobo/papergenerator/backend")

OUTPUT_DIR = Path("/home/sirobo/ANNABIL/Project Papergenerator_Annabil/A transit output web")
PAPER_JSON_SRC = Path("/home/sirobo/papergenerator/backend/user/anabilhisyam23/Arsitektur_Keamanan_End-to-End_Transfer_Data_IoT_Sensor_ke_GUI_Berbasis_Cloud/paper.json")

KELOMPOK1 = ["AEJ","DJLIT","EASR","ELCTRICES","ELKOLIND","ENERGIUPM",
             "El-Usrah","ICET","ICIMECE","ICONIE","ICOSEG","IJB","IJECE",
             "IJEECS","IJIMS","IJITEE","IJRED"]
# AMORI excluded (fails)

def main():
    from main import app, _get_builder_for_journal
    with app.app_context():
        # Read the paper JSON from user folder
        with open(PAPER_JSON_SRC, 'r', encoding='utf-8') as f:
            paper_json = json.load(f)
        
        paper_data = paper_json.get('paper_data', paper_json)
        # Handle both old format (paper_data = flat content) and new format (paper_data = {"paper": content})
        if isinstance(paper_data, dict) and 'paper' in paper_data:
            paper_data = paper_data['paper']
        title = paper_data.get('title', 'untitled')[:60]
        print(f"Paper: {title}")
        print(f"  figures={len(paper_data.get('figures',[]))}")
        
        # Count inline gambar
        g_count = 0
        for sk in range(1,6):
            s = paper_data.get(f'section{sk}', {})
            c = s.get('content', [])
            if isinstance(c, list):
                for item in c:
                    if isinstance(item, dict) and item.get('id') in ('gambar','image'):
                        g_count += 1
        print(f"  inline gambar={g_count}")
        
        temp_dir = Path("/home/sirobo/papergenerator/backend/user/batch_test/export")
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        results = []
        for journal in KELOMPOK1:
            # Write temp JSON (same content, different journal)
            paper_data["journal"] = journal
            json_path = temp_dir / f"_paper_{journal}.json"
            # Wrap in paper_data structure if generator expects it
            wrapped = {"judul": paper_data.get("title",""), "paper_data": {"paper": paper_data}}
            json_path.write_text(json.dumps(wrapped, ensure_ascii=False, indent=2), encoding="utf-8")
            
            safe_title = re.sub(r"[^a-zA-Z0-9_\-.]+", "_", str(title)).strip("_")[:35]
            out_path = OUTPUT_DIR / f"{journal}_{safe_title}.docx"
            
            try:
                canonical, builder = _get_builder_for_journal(journal)
                builder(str(json_path), str(out_path))
                
                if out_path.exists() and out_path.stat().st_size > 5000:
                    size_kb = out_path.stat().st_size / 1024
                    results.append((journal, f"OK ({size_kb:.0f}KB)"))
                    print(f"  {journal}: OK -> {out_path.name} ({size_kb:.0f}KB)")
                else:
                    results.append((journal, "FAIL (small)"))
                    print(f"  {journal}: FAIL - too small")
            except Exception as e:
                results.append((journal, f"FAIL: {str(e)[:80]}"))
                print(f"  {journal}: {e}")
            
            json_path.unlink(missing_ok=True)
        
        print("\n=== RESULTS ===")
        for j, r in results:
            print(f"{j:12s} | {r}")

if __name__ == "__main__":
    main()