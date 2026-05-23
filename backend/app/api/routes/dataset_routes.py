import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.application.datasource_use_cases.import_file_dataset import ImportFileDataset
from app.infrastructure.catalog.dataset_catalog import DatasetCatalog
from app.infrastructure.cleaning.dataset_cleaning_service import DataCleaningService
from app.infrastructure.jobs.job_store import JobStore
from app.infrastructure.settings import settings
from app.infrastructure.storage.local_dataset_store import LocalDatasetStore

router = APIRouter(prefix="/datasets", tags=["datasets"])


class CleaningRequest(BaseModel):
    operation_ids: list[str] | None = Field(default=None)


@router.post("/import/file")
async def import_file(file: UploadFile) -> dict[str, Any]:
    dataset_store = LocalDatasetStore()
    use_case = ImportFileDataset(dataset_store)
    try:
        dataset = await use_case.execute(file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    catalog = DatasetCatalog()
    metadata = catalog.get_dataset(dataset.id, dataset.current_version_id)
    return metadata


@router.post("/import/file/job")
async def create_import_file_job(
    file: UploadFile,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    job_store = JobStore()
    original_name = file.filename or "source.csv"
    job = job_store.create("import_file_dataset", {"file_name": original_name})
    temp_path = _save_job_upload(job["job_id"], file, original_name)
    background_tasks.add_task(_run_import_file_job, job["job_id"], temp_path, original_name)
    return job


@router.get("")
async def list_datasets() -> list[dict[str, Any]]:
    return DatasetCatalog().list_datasets()


@router.get("/{dataset_id}/versions/{version_id}/profile")
async def get_profile(dataset_id: str, version_id: str) -> dict[str, Any]:
    return DatasetCatalog().get_profile(dataset_id, version_id)


@router.get("/{dataset_id}/versions/{version_id}/analysis")
async def get_analysis(dataset_id: str, version_id: str) -> dict[str, Any]:
    return DatasetCatalog().get_analysis(dataset_id, version_id)


@router.get("/{dataset_id}/versions/{version_id}/preview")
async def get_preview(dataset_id: str, version_id: str, limit: int = 50) -> dict[str, Any]:
    try:
        return DataCleaningService().preview_rows(dataset_id, version_id, limit)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{dataset_id}/versions/{version_id}/cleaning-plan")
async def get_cleaning_plan(dataset_id: str, version_id: str) -> dict[str, Any]:
    try:
        return DataCleaningService().cleaning_plan(dataset_id, version_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{dataset_id}/versions/{version_id}/cleaning-preview")
async def preview_cleaning(
    dataset_id: str,
    version_id: str,
    request: CleaningRequest,
) -> dict[str, Any]:
    try:
        return DataCleaningService().preview_cleaning(dataset_id, version_id, request.operation_ids)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{dataset_id}/versions/{version_id}/cleaning-execute")
async def execute_cleaning(
    dataset_id: str,
    version_id: str,
    request: CleaningRequest,
) -> dict[str, Any]:
    try:
        return await DataCleaningService().execute_cleaning(
            dataset_id,
            version_id,
            request.operation_ids,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{dataset_id}/versions/{version_id}/cleaning-execute/job")
async def create_cleaning_job(
    dataset_id: str,
    version_id: str,
    request: CleaningRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    DatasetCatalog().get_dataset(dataset_id, version_id)
    job = JobStore().create(
        "clean_dataset_version",
        {
            "dataset_id": dataset_id,
            "version_id": version_id,
            "operation_ids": request.operation_ids,
        },
    )
    background_tasks.add_task(
        _run_cleaning_job,
        job["job_id"],
        dataset_id,
        version_id,
        request.operation_ids,
    )
    return job


def _save_job_upload(job_id: str, file: UploadFile, original_name: str) -> Path:
    suffix = Path(original_name).suffix.lower()
    temp_dir = settings.storage_root / "tmp" / "jobs" / job_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"source{suffix}"
    with temp_path.open("wb") as target:
        shutil.copyfileobj(file.file, target)
    return temp_path


async def _run_import_file_job(job_id: str, temp_path: Path, original_name: str) -> None:
    job_store = JobStore()
    job_store.mark_running(job_id)
    try:
        with temp_path.open("rb") as source:
            dataset = await LocalDatasetStore().save_local_file(source, original_name)
        metadata = DatasetCatalog().get_dataset(dataset.id, dataset.current_version_id)
        job_store.mark_succeeded(job_id, metadata)
    except Exception as exc:
        job_store.mark_failed(job_id, str(exc))
    finally:
        shutil.rmtree(temp_path.parent, ignore_errors=True)


async def _run_cleaning_job(
    job_id: str,
    dataset_id: str,
    version_id: str,
    operation_ids: list[str] | None,
) -> None:
    job_store = JobStore()
    job_store.mark_running(job_id)
    try:
        metadata = await DataCleaningService().execute_cleaning(
            dataset_id,
            version_id,
            operation_ids,
        )
        job_store.mark_succeeded(job_id, metadata)
    except Exception as exc:
        job_store.mark_failed(job_id, str(exc))
