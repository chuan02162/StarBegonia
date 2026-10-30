"""RQ job.meta progress helpers — readable by /jobs/<id> poll endpoints."""

from __future__ import annotations

from typing import Any


def set_progress(
    *,
    stage: str = "",
    current: int = 0,
    total: int = 0,
    message: str = "",
) -> None:
    try:
        from rq import get_current_job
    except Exception:
        return
    job = get_current_job()
    if not job:
        return
    total_n = max(int(total), 0)
    current_n = max(int(current), 0)
    if total_n > 0:
        current_n = min(current_n, total_n)
        percent = int(round(100.0 * current_n / total_n))
    else:
        percent = 0
    job.meta["progress"] = {
        "stage": stage or "",
        "current": current_n,
        "total": total_n,
        "percent": percent,
        "message": message or "",
    }
    try:
        job.save_meta()
    except Exception:
        pass


def job_progress_payload(job: Any) -> dict[str, Any] | None:
    meta = getattr(job, "meta", None) or {}
    progress = meta.get("progress")
    if isinstance(progress, dict):
        return progress
    return None
