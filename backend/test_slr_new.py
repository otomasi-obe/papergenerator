#!/usr/bin/env python3
"""Test SLR new orchestrator end-to-end."""
import sys
sys.path.insert(0, "/home/sirobo/papergenerator/backend")

from tools.Literatur.slr import start_slr_job, get_slr_job
import time

job_id = start_slr_job(
    paper_id="c4cd4eb17f7e",
    keyword="deep learning tuberculosis",
    top_n=10,
    user_id=1,
)
print(f"Job ID: {job_id}")

# Poll for progress
for i in range(15):
    time.sleep(2)
    job = get_slr_job(job_id)
    if job is None:
        print(f"  [{i}] Job not found!")
        break
    status = job.get("status", "unknown")
    progress = job.get("progress", 0)
    stage = job.get("stage", "?")
    prog_msg = job.get("progress_message", "")
    src_done = job.get("sources_completed", [])
    src_total = job.get("sources_total", 0)
    papers = job.get("all_papers_count", 0)
    
    print(f"  [{i}] status={status} progress={progress}% stage={stage}")
    if prog_msg:
        print(f"       detail: {prog_msg[:80]}")
    print(f"       sources: {len(src_done)}/{src_total} | papers: {papers}")
    
    if status in ("done", "complete", "completed", "error", "cancelled"):
        results = job.get("results") or []
        print(f"  FINAL: {status} with {len(results)} papers")
        if results:
            print(f"  First paper: {results[0].get('title', '?')[:80]}")
        break
else:
    print("  TIMEOUT: still running after 30s")
