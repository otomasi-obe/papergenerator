"""Thread-safe job tracker for active paper generation jobs.

Maps paper_id to job_id so concurrent requests for the same paper
can detect and cancel a running job before starting a new one.
"""

import threading

_active_jobs_by_paper: dict[str, str] = {}
_active_jobs_lock = threading.Lock()


def register_active_job(paper_id: str, job_id: str) -> None:
    """Register a job as active for the given paper_id.

    If a job is already registered for this paper_id, it will be
    overwritten with the new job_id.

    Args:
        paper_id: Unique identifier for the paper.
        job_id: Unique identifier for the background job.
    """
    with _active_jobs_lock:
        _active_jobs_by_paper[paper_id] = job_id


def clear_active_job(paper_id: str) -> None:
    """Remove the active job entry for the given paper_id.

    Safe to call even if no job is registered for the paper_id.

    Args:
        paper_id: Unique identifier for the paper.
    """
    with _active_jobs_lock:
        _active_jobs_by_paper.pop(paper_id, None)
