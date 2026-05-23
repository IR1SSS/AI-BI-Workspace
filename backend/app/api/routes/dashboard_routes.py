from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.infrastructure.catalog.dataset_catalog import DatasetCatalog
from app.infrastructure.jobs.job_store import JobStore
from app.infrastructure.report.report_agent import ReportAgent
from app.infrastructure.visualization.chart_title_formatter import ChartTitleFormatter

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


@router.get("/{dashboard_id}")
async def get_dashboard(dashboard_id: str) -> dict[str, str]:
    return {"dashboard_id": dashboard_id, "status": "draft"}


@router.get("/by-dataset/{dataset_id}/versions/{version_id}")
async def get_dashboard_by_dataset(dataset_id: str, version_id: str) -> dict[str, Any]:
    catalog = DatasetCatalog()
    return _decorate_dashboard(
        catalog.get_dashboard(dataset_id, version_id),
        catalog.get_dataset(dataset_id, version_id),
        catalog.get_report(dataset_id, version_id),
    )


@router.post("/by-dataset/{dataset_id}/versions/{version_id}/report")
async def generate_dashboard_report(dataset_id: str, version_id: str) -> dict[str, Any]:
    return await ReportAgent().generate(dataset_id, version_id)


@router.post("/by-dataset/{dataset_id}/versions/{version_id}/report/job")
async def create_dashboard_report_job(
    dataset_id: str,
    version_id: str,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    DatasetCatalog().get_dataset(dataset_id, version_id)
    job = JobStore().create(
        "generate_dashboard_report",
        {"dataset_id": dataset_id, "version_id": version_id},
    )
    background_tasks.add_task(_run_dashboard_report_job, job["job_id"], dataset_id, version_id)
    return job


@router.delete("/by-dataset/{dataset_id}/versions/{version_id}")
async def delete_dataset_version(dataset_id: str, version_id: str) -> dict[str, bool]:
    try:
        return DatasetCatalog().delete_dataset_version(dataset_id, version_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("")
async def list_dashboards() -> list[dict[str, Any]]:
    catalog = DatasetCatalog()
    dashboards: list[dict[str, Any]] = []
    for dataset in catalog.list_datasets():
        dashboard = catalog.get_dashboard(dataset["dataset_id"], dataset["version_id"])
        report = catalog.get_report(dataset["dataset_id"], dataset["version_id"])
        dashboards.append(_decorate_dashboard(dashboard, dataset, report))

    return dashboards


def _decorate_dashboard(
    dashboard: dict[str, Any],
    metadata: dict[str, Any],
    report: dict[str, Any] | None,
) -> dict[str, Any]:
    file_name = str(metadata.get("file_name") or dashboard.get("title") or "Dataset")
    decorated = dict(dashboard)
    decorated["file_name"] = file_name
    decorated["title"] = f"{file_name} Dashboard Draft"
    title_formatter = ChartTitleFormatter()
    decorated["cards"] = [
        title_formatter.decorate_card(card)
        for card in dashboard.get("cards", [])
        if card.get("type") != "text"
    ]
    decorated["report"] = report
    return decorated


async def _run_dashboard_report_job(job_id: str, dataset_id: str, version_id: str) -> None:
    job_store = JobStore()
    job_store.mark_running(job_id)
    try:
        report = await ReportAgent().generate(dataset_id, version_id)
        job_store.mark_succeeded(job_id, report)
    except Exception as exc:
        job_store.mark_failed(job_id, str(exc))
