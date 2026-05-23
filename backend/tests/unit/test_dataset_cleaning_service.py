import json

import pandas as pd
from app.infrastructure.cleaning.dataset_cleaning_service import DataCleaningService
from app.infrastructure.settings import settings


def test_cleaning_plan_detects_index_empty_rows_and_missing_values(tmp_path):
    original_root = settings.storage_root
    settings.storage_root = tmp_path
    try:
        parquet_path = _write_dataset(
            tmp_path,
            pd.DataFrame(
                {
                    "Unnamed: 0": [1, 2, None],
                    "category": ["A", None, None],
                    "amount": [10.0, None, None],
                }
            ),
        )
        _write_profile(tmp_path, parquet_path)

        plan = DataCleaningService().cleaning_plan("dataset-1", "v0001")
    finally:
        settings.storage_root = original_root

    operation_types = {operation["operation_type"] for operation in plan["operations"]}
    assert operation_types >= {"drop_columns", "drop_empty_rows", "fill_missing"}
    assert any(operation["target_column"] == "amount" for operation in plan["operations"])


def test_execute_cleaning_creates_new_dataset_version(tmp_path):
    original_root = settings.storage_root
    settings.storage_root = tmp_path
    try:
        parquet_path = _write_dataset(
            tmp_path,
            pd.DataFrame(
                {
                    "Unnamed: 0": [1, 2],
                    "category": ["A", None],
                    "amount": [10.0, None],
                }
            ),
        )
        _write_profile(tmp_path, parquet_path)

        metadata = _run(DataCleaningService().execute_cleaning("dataset-1", "v0001"))
        cleaned = pd.read_parquet(tmp_path / "warehouse" / "dataset-1" / "v0002" / "data.parquet")
    finally:
        settings.storage_root = original_root

    assert metadata["version_id"] == "v0002"
    assert metadata["parent_version_id"] == "v0001"
    assert "Unnamed: 0" not in cleaned.columns
    assert cleaned["amount"].isna().sum() == 0


def test_cleaning_plan_can_remove_duplicate_rows(tmp_path):
    original_root = settings.storage_root
    settings.storage_root = tmp_path
    try:
        parquet_path = _write_dataset(
            tmp_path,
            pd.DataFrame(
                {
                    "category": ["A", "A", "B"],
                    "amount": [10.0, 10.0, 20.0],
                }
            ),
        )
        _write_profile(tmp_path, parquet_path)

        service = DataCleaningService()
        plan = service.cleaning_plan("dataset-1", "v0001")
        preview = service.preview_cleaning(
            "dataset-1",
            "v0001",
            ["drop-duplicate-rows"],
        )
    finally:
        settings.storage_root = original_root

    assert any(
        operation["operation_type"] == "drop_duplicate_rows" for operation in plan["operations"]
    )
    assert preview["row_count_delta"] == -1


def _write_dataset(root, dataframe: pd.DataFrame):
    warehouse_dir = root / "warehouse" / "dataset-1" / "v0001"
    raw_dir = root / "raw" / "dataset-1" / "v0001"
    warehouse_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    parquet_path = warehouse_dir / "data.parquet"
    dataframe.to_parquet(parquet_path, index=False)
    (raw_dir / "source.csv").write_text("placeholder", encoding="utf-8")
    metadata = {
        "dataset_id": "dataset-1",
        "version_id": "v0001",
        "file_name": "orders.csv",
        "raw_path": str(raw_dir / "source.csv"),
        "parquet_path": str(parquet_path),
        "created_at": "2026-01-01T00:00:00+00:00",
        "row_count": len(dataframe),
        "column_count": len(dataframe.columns),
        "profile_status": "ready",
        "dashboard_status": "ready",
    }
    (warehouse_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    return parquet_path


def _write_profile(root, parquet_path) -> None:
    from app.infrastructure.profiling.parquet_profiler import ParquetProfiler

    profile = ParquetProfiler().profile("v0001", parquet_path)
    version_dir = root / "warehouse" / "dataset-1" / "v0001"
    (version_dir / "profile.json").write_text(json.dumps(profile), encoding="utf-8")
    (version_dir / "dashboard.json").write_text(json.dumps({"cards": []}), encoding="utf-8")
    (version_dir / "analysis.json").write_text(json.dumps({"chart_plan": []}), encoding="utf-8")


def _run(awaitable):
    import asyncio

    return asyncio.run(awaitable)
