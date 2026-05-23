import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.infrastructure.settings import settings


class JobStore:
    def create(self, job_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        now = self._now()
        job = {
            "job_id": str(uuid4()),
            "job_type": job_type,
            "status": "pending",
            "payload": payload or {},
            "result": None,
            "error": "",
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "finished_at": None,
        }
        self._write(job)
        return job

    def get(self, job_id: str) -> dict[str, Any]:
        path = self._path(job_id)
        if not path.exists():
            raise FileNotFoundError(f"Job does not exist: {job_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        jobs = [
            json.loads(path.read_text(encoding="utf-8")) for path in self._root().glob("*.json")
        ]
        return sorted(jobs, key=lambda job: str(job.get("created_at") or ""), reverse=True)[:limit]

    def mark_running(self, job_id: str) -> dict[str, Any]:
        job = self.get(job_id)
        now = self._now()
        job.update({"status": "running", "started_at": now, "updated_at": now})
        self._write(job)
        return job

    def mark_succeeded(self, job_id: str, result: dict[str, Any]) -> dict[str, Any]:
        job = self.get(job_id)
        now = self._now()
        job.update({"status": "succeeded", "result": result, "updated_at": now, "finished_at": now})
        self._write(job)
        return job

    def mark_failed(self, job_id: str, error: str) -> dict[str, Any]:
        job = self.get(job_id)
        now = self._now()
        job.update({"status": "failed", "error": error, "updated_at": now, "finished_at": now})
        self._write(job)
        return job

    def _write(self, job: dict[str, Any]) -> None:
        path = self._path(str(job["job_id"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")

    def _path(self, job_id: str) -> Path:
        return self._root() / f"{job_id}.json"

    def _root(self) -> Path:
        return settings.storage_root / "jobs"

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()
