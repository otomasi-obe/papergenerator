#!/usr/bin/env python3
"""Test SLR with Flask context — verify DB save works."""
import sys
sys.path.insert(0, "/home/sirobo/papergenerator/backend")

from main import app
from tools.Literatur.slr import start_slr_job, get_slr_job
import time

with app.app_context():
    job_id = start_slr_job(paper_id="c4cd4eb17f7e", keyword="deep learning tuberculosis", top_n=10, user_id=1)
    print(f"Job ID: {job_id}")
    
    for i in range(15):
        time.sleep(2)
        job = get_slr_job(job_id)
        status = job.get("status", "?")
        progress = job.get("progress", 0)
        stage = job.get("stage", "?")
        detail = job.get("progress_message", "")[:80]
        papers = job.get("all_papers_count", 0)
        print(f"  [{i}] {status} {progress}% stage={stage} papers={papers} msg={detail}")
        
        if status in ("done", "complete", "completed", "error"):
            results = job.get("results") or []
            print(f"  FINAL: {len(results)} ranked results")
            if results:
                t = results[0].get("title", "?")
                print(f"  Top: {t[:60]}")
            break
    
    # Check DB
    from utils.database.models import LiteratureItem
    items = LiteratureItem.query.filter_by(paper_id="c4cd4eb17f7e").all()
    print(f"  DB LiteratureItems for this paper: {len(items)}")
    for item in items[:3]:
        print(f"    - [{item.source}] {item.title[:60]} (doi={item.doi})")
