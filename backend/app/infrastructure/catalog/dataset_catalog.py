import json
import shutil
from pathlib import Path
from typing import Any

from app.infrastructure.settings import settings


class DatasetCatalog:
    def list_datasets(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        warehouse_root = settings.storage_root / "warehouse"
        if not warehouse_root.exists():
            return records

        for metadata_path in warehouse_root.glob("*/v*/metadata.json"):
            records.append(self._read_json(metadata_path))

        return sorted(records, key=lambda item: str(item.get("created_at", "")), reverse=True)

    def get_dataset(self, dataset_id: str, version_id: str) -> dict[str, Any]:
        return self._read_json(self._version_dir(dataset_id, version_id) / "metadata.json")

    def get_profile(self, dataset_id: str, version_id: str) -> dict[str, Any]:
        return self._read_json(self._version_dir(dataset_id, version_id) / "profile.json")

    def get_dashboard(self, dataset_id: str, version_id: str) -> dict[str, Any]:
        return self._read_json(self._version_dir(dataset_id, version_id) / "dashboard.json")

    def get_analysis(self, dataset_id: str, version_id: str) -> dict[str, Any]:
        return self._read_json(self._version_dir(dataset_id, version_id) / "analysis.json")

    def get_report(self, dataset_id: str, version_id: str) -> dict[str, Any] | None:
        path = self._version_dir(dataset_id, version_id) / "report.json"
        if not path.exists():
            return None
        return self._read_json(path)

    def delete_dataset_version(self, dataset_id: str, version_id: str) -> dict[str, bool]:
        version_dir = self._version_dir(dataset_id, version_id)
        if not version_dir.exists():
            raise FileNotFoundError(f"Dataset version does not exist: {version_dir}")

        storage_root = settings.storage_root.resolve()
        paths = [
            version_dir,
            settings.storage_root / "raw" / dataset_id / version_id,
        ]
        for path in paths:
            resolved_path = path.resolve()
            if not str(resolved_path).startswith(str(storage_root)):
                raise ValueError(f"Refusing to delete path outside storage root: {resolved_path}")
            if resolved_path.exists():
                shutil.rmtree(resolved_path)

        self._remove_empty_parent(settings.storage_root / "warehouse" / dataset_id)
        self._remove_empty_parent(settings.storage_root / "raw" / dataset_id)
        return {"deleted": True}

    def write_dataset_artifacts(
        self,
        dataset_id: str,
        version_id: str,
        metadata: dict[str, Any],
        profile: dict[str, Any],
        dashboard: dict[str, Any],
        analysis: dict[str, Any] | None = None,
    ) -> None:
        version_dir = self._version_dir(dataset_id, version_id)
        version_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(version_dir / "metadata.json", metadata)
        self._write_json(version_dir / "profile.json", profile)
        self._write_json(version_dir / "dashboard.json", dashboard)
        if analysis is not None:
            self._write_json(version_dir / "analysis.json", analysis)

    def _version_dir(self, dataset_id: str, version_id: str) -> Path:
        return settings.storage_root / "warehouse" / dataset_id / version_id

    def _read_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(f"Catalog artifact does not exist: {path}")

        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _remove_empty_parent(self, path: Path) -> None:
        if path.exists() and not any(path.iterdir()):
            path.rmdir()
