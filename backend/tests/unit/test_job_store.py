from app.infrastructure.jobs.job_store import JobStore
from app.infrastructure.settings import settings


def test_job_store_tracks_lifecycle(tmp_path):
    original_root = settings.storage_root
    settings.storage_root = tmp_path
    try:
        store = JobStore()
        created = store.create("import_file_dataset", {"file_name": "sales.csv"})
        running = store.mark_running(created["job_id"])
        succeeded = store.mark_succeeded(created["job_id"], {"dataset_id": "dataset-1"})
        loaded = store.get(created["job_id"])
        recent = store.list_recent()
    finally:
        settings.storage_root = original_root

    assert created["status"] == "pending"
    assert running["status"] == "running"
    assert succeeded["status"] == "succeeded"
    assert loaded["result"] == {"dataset_id": "dataset-1"}
    assert recent[0]["job_id"] == created["job_id"]


def test_job_store_tracks_failures(tmp_path):
    original_root = settings.storage_root
    settings.storage_root = tmp_path
    try:
        store = JobStore()
        created = store.create("import_file_dataset")
        failed = store.mark_failed(created["job_id"], "bad file")
    finally:
        settings.storage_root = original_root

    assert failed["status"] == "failed"
    assert failed["error"] == "bad file"
