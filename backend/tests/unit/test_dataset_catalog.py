import json

from app.infrastructure.catalog.dataset_catalog import DatasetCatalog
from app.infrastructure.settings import settings


def test_dataset_catalog_deletes_dataset_version_and_raw_cache(tmp_path):
    original_root = settings.storage_root
    settings.storage_root = tmp_path
    try:
        warehouse_dir = tmp_path / "warehouse" / "dataset-1" / "v0001"
        raw_dir = tmp_path / "raw" / "dataset-1" / "v0001"
        warehouse_dir.mkdir(parents=True)
        raw_dir.mkdir(parents=True)
        (warehouse_dir / "metadata.json").write_text(
            json.dumps({"dataset_id": "dataset-1"}), encoding="utf-8"
        )
        (raw_dir / "source.csv").write_text("a\n1\n", encoding="utf-8")

        result = DatasetCatalog().delete_dataset_version("dataset-1", "v0001")
    finally:
        settings.storage_root = original_root

    assert result == {"deleted": True}
    assert not warehouse_dir.exists()
    assert not raw_dir.exists()
