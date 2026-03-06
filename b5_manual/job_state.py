# File: athena/job_state.py
# Version: v1.0 — Shared job state + helpers (thread-safe)

from __future__ import annotations
import threading
import uuid
from datetime import datetime
from typing import Dict, Any

JOBS: Dict[str, Dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()

def new_job(stage: str) -> str:
    job_id = str(uuid.uuid4())
    with JOBS_LOCK:
        JOBS[job_id] = {
            "stage": stage,
            "total": 0,
            "done": 0,
            "percent": 0,
            "status": "starting",
            "started": datetime.now().isoformat(),
            "log": [],
            "result": None,
            "errors": [],
            "skipped": [],
        }
    return job_id

def update_job(job_id: str, **kw):
    with JOBS_LOCK:
        j = JOBS.get(job_id)
        if not j:
            return
        j.update(kw)
        if j.get("total"):
            j["percent"] = int(100 * j.get("done", 0) / max(1, j["total"]))

def bump(job_id: str, n: int = 1):
    with JOBS_LOCK:
        j = JOBS.get(job_id)
        if not j:
            return
        j["done"] = int(j.get("done", 0) + n)
        if j.get("total"):
            j["percent"] = int(100 * j["done"] / max(1, j["total"]))

def get_job(job_id: str) -> Dict[str, Any]:
    with JOBS_LOCK:
        return JOBS.get(job_id, {"ok": False, "error": "job not found"})