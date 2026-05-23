from typing import Any

from fastapi import APIRouter, HTTPException

from app.infrastructure.jobs.job_store import JobStore

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
async def list_jobs(limit: int = 20) -> list[dict[str, Any]]:
    return JobStore().list_recent(limit)


@router.get("/{job_id}")
async def get_job(job_id: str) -> dict[str, Any]:
    try:
        return JobStore().get(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
