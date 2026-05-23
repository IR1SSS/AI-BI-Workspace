import asyncio

from app.api.routes import dashboard_routes, dataset_routes
from app.infrastructure.jobs.job_store import JobStore
from app.infrastructure.settings import settings


def test_cleaning_background_job_marks_success(tmp_path, monkeypatch):
    class FakeCleaningService:
        async def execute_cleaning(self, dataset_id, version_id, operation_ids):
            return {
                "dataset_id": dataset_id,
                "version_id": "v0002",
                "operation_ids": operation_ids,
            }

    monkeypatch.setattr(dataset_routes, "DataCleaningService", FakeCleaningService)

    original_root = settings.storage_root
    settings.storage_root = tmp_path
    try:
        job = JobStore().create("clean_dataset_version")
        asyncio.run(
            dataset_routes._run_cleaning_job(
                job["job_id"],
                "dataset-1",
                "v0001",
                ["drop-duplicate-rows"],
            )
        )
        loaded = JobStore().get(job["job_id"])
    finally:
        settings.storage_root = original_root

    assert loaded["status"] == "succeeded"
    assert loaded["result"]["version_id"] == "v0002"


def test_report_background_job_marks_success(tmp_path, monkeypatch):
    class FakeReportAgent:
        async def generate(self, dataset_id, version_id):
            return {
                "title": "Report",
                "dataset_id": dataset_id,
                "version_id": version_id,
            }

    monkeypatch.setattr(dashboard_routes, "ReportAgent", FakeReportAgent)

    original_root = settings.storage_root
    settings.storage_root = tmp_path
    try:
        job = JobStore().create("generate_dashboard_report")
        asyncio.run(
            dashboard_routes._run_dashboard_report_job(
                job["job_id"],
                "dataset-1",
                "v0001",
            )
        )
        loaded = JobStore().get(job["job_id"])
    finally:
        settings.storage_root = original_root

    assert loaded["status"] == "succeeded"
    assert loaded["result"]["title"] == "Report"
