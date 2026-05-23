import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from app.infrastructure.analysis.ai_analysis_planner import AIAnalysisPlanner
from app.infrastructure.catalog.dataset_catalog import DatasetCatalog
from app.infrastructure.profiling.parquet_profiler import ParquetProfiler
from app.infrastructure.settings import settings
from app.infrastructure.visualization.dashboard_generator import DashboardGenerator


class DataCleaningService:
    def __init__(self) -> None:
        self.catalog = DatasetCatalog()
        self.profiler = ParquetProfiler()
        self.analysis_planner = AIAnalysisPlanner()
        self.dashboard_generator = DashboardGenerator()

    def preview_rows(self, dataset_id: str, version_id: str, limit: int = 50) -> dict[str, Any]:
        metadata = self.catalog.get_dataset(dataset_id, version_id)
        dataframe = pd.read_parquet(Path(metadata["parquet_path"])).head(max(1, min(limit, 200)))
        return {
            "columns": [str(column) for column in dataframe.columns],
            "rows": self._records(dataframe),
        }

    def cleaning_plan(self, dataset_id: str, version_id: str) -> dict[str, Any]:
        metadata = self.catalog.get_dataset(dataset_id, version_id)
        profile = self.catalog.get_profile(dataset_id, version_id)
        dataframe = pd.read_parquet(Path(metadata["parquet_path"]))
        operations = self._propose_operations(profile, dataframe)
        return {
            "dataset_id": dataset_id,
            "version_id": version_id,
            "operation_count": len(operations),
            "operations": operations,
        }

    def preview_cleaning(
        self,
        dataset_id: str,
        version_id: str,
        operation_ids: list[str] | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        metadata = self.catalog.get_dataset(dataset_id, version_id)
        dataframe = pd.read_parquet(Path(metadata["parquet_path"]))
        plan = self.cleaning_plan(dataset_id, version_id)
        cleaned = self._apply_operations(dataframe, plan["operations"], operation_ids)
        return {
            "plan": plan,
            "before": self._preview_payload(dataframe, limit),
            "after": self._preview_payload(cleaned, limit),
            "row_count_delta": int(len(cleaned) - len(dataframe)),
            "column_count_delta": int(len(cleaned.columns) - len(dataframe.columns)),
        }

    async def execute_cleaning(
        self,
        dataset_id: str,
        version_id: str,
        operation_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        source_metadata = self.catalog.get_dataset(dataset_id, version_id)
        dataframe = pd.read_parquet(Path(source_metadata["parquet_path"]))
        plan = self.cleaning_plan(dataset_id, version_id)
        cleaned = self._apply_operations(dataframe, plan["operations"], operation_ids)
        new_version_id = self._next_version_id(dataset_id)
        warehouse_dir = settings.storage_root / "warehouse" / dataset_id / new_version_id
        warehouse_dir.mkdir(parents=True, exist_ok=True)

        parquet_path = warehouse_dir / "data.parquet"
        cleaned.to_parquet(parquet_path, index=False)
        profile = self.profiler.profile(new_version_id, parquet_path)
        analysis = await self.analysis_planner.plan(profile)
        dashboard = self.dashboard_generator.generate(
            dataset_id,
            new_version_id,
            str(source_metadata.get("file_name") or "Dataset"),
            profile,
            cleaned,
            analysis,
        )
        metadata = self._cleaned_metadata(
            source_metadata,
            new_version_id,
            parquet_path,
            profile,
            plan,
        )
        self.catalog.write_dataset_artifacts(
            dataset_id,
            new_version_id,
            metadata,
            profile,
            dashboard,
            analysis,
        )
        (warehouse_dir / "cleaning_plan.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._copy_raw_source(dataset_id, version_id, new_version_id)
        return metadata

    def _propose_operations(
        self,
        profile: dict[str, Any],
        dataframe: pd.DataFrame,
    ) -> list[dict[str, Any]]:
        operations = self._drop_index_operations(profile)
        operations.extend(self._drop_duplicate_row_operations(profile))
        empty_rows = int(dataframe.isna().all(axis=1).sum())
        if empty_rows:
            operations.append(
                self._operation(
                    "drop-empty-rows",
                    "drop_empty_rows",
                    None,
                    {"empty_row_count": empty_rows},
                    f"Remove {empty_rows} fully empty row(s).",
                )
            )
        operations.extend(self._fill_missing_operations(profile, dataframe))
        return operations

    def _drop_duplicate_row_operations(self, profile: dict[str, Any]) -> list[dict[str, Any]]:
        duplicate_issues = [
            issue
            for issue in profile.get("quality_issues", [])
            if issue.get("type") == "duplicate_rows"
        ]
        if not duplicate_issues:
            return []
        duplicate_count = int(duplicate_issues[0].get("count") or 0)
        return [
            self._operation(
                "drop-duplicate-rows",
                "drop_duplicate_rows",
                None,
                {"duplicate_row_count": duplicate_count},
                f"Remove {duplicate_count} duplicate row(s).",
            )
        ]

    def _drop_index_operations(self, profile: dict[str, Any]) -> list[dict[str, Any]]:
        columns = [
            column["name"]
            for column in profile.get("columns", [])
            if column.get("is_probable_index")
        ]
        if not columns:
            return []
        return [
            self._operation(
                "drop-probable-index-columns",
                "drop_columns",
                None,
                {"columns": columns},
                "Remove exported dataframe index columns from the analytical dataset.",
            )
        ]

    def _fill_missing_operations(
        self,
        profile: dict[str, Any],
        dataframe: pd.DataFrame,
    ) -> list[dict[str, Any]]:
        operations: list[dict[str, Any]] = []
        for column in profile.get("columns", []):
            column_name = str(column.get("name") or "")
            if not column_name or int(column.get("null_count") or 0) <= 0:
                continue
            if column_name not in dataframe.columns:
                continue
            fill_value = self._fill_value(dataframe[column_name], bool(column.get("is_numeric")))
            if fill_value is None:
                continue
            operations.append(
                self._operation(
                    f"fill-missing-{self._slug(column_name)}",
                    "fill_missing",
                    column_name,
                    {"value": fill_value, "null_count": int(column["null_count"])},
                    f"Fill missing values in {column_name} with {fill_value}.",
                )
            )
        return operations

    def _apply_operations(
        self,
        dataframe: pd.DataFrame,
        operations: list[dict[str, Any]],
        operation_ids: list[str] | None,
    ) -> pd.DataFrame:
        selected = set(operation_ids) if operation_ids else None
        cleaned = dataframe.copy()
        for operation in operations:
            if selected is not None and operation["id"] not in selected:
                continue
            if operation["operation_type"] == "drop_columns":
                columns = [
                    column
                    for column in operation["parameters"]["columns"]
                    if column in cleaned.columns
                ]
                cleaned = cleaned.drop(columns=columns)
            elif operation["operation_type"] == "drop_empty_rows":
                cleaned = cleaned.dropna(how="all")
            elif operation["operation_type"] == "drop_duplicate_rows":
                cleaned = cleaned.drop_duplicates()
            elif operation["operation_type"] == "fill_missing":
                column = operation.get("target_column")
                if column in cleaned.columns:
                    cleaned[column] = cleaned[column].fillna(operation["parameters"]["value"])
        return cleaned.reset_index(drop=True)

    def _fill_value(self, series: pd.Series, is_numeric: bool) -> Any:
        non_null = series.dropna()
        if non_null.empty:
            return None
        if is_numeric:
            value = pd.to_numeric(non_null, errors="coerce").dropna().median()
            return None if pd.isna(value) else float(value)
        mode = non_null.astype(str).mode()
        return None if mode.empty else mode.iloc[0]

    def _cleaned_metadata(
        self,
        source_metadata: dict[str, Any],
        version_id: str,
        parquet_path: Path,
        profile: dict[str, Any],
        plan: dict[str, Any],
    ) -> dict[str, Any]:
        metadata = dict(source_metadata)
        raw_name = Path(str(source_metadata.get("raw_path") or "source")).name
        raw_path = (
            settings.storage_root / "raw" / source_metadata["dataset_id"] / version_id / raw_name
        )
        metadata.update(
            {
                "version_id": version_id,
                "parent_version_id": source_metadata.get("version_id"),
                "raw_path": str(raw_path),
                "parquet_path": str(parquet_path),
                "created_at": datetime.now(UTC).isoformat(),
                "row_count": profile["row_count"],
                "column_count": profile["column_count"],
                "profile_status": "ready",
                "dashboard_status": "ready",
                "cleaning_status": "ready",
                "cleaning_operation_count": plan["operation_count"],
            }
        )
        return metadata

    def _next_version_id(self, dataset_id: str) -> str:
        dataset_dir = settings.storage_root / "warehouse" / dataset_id
        version_numbers = []
        for path in dataset_dir.glob("v*"):
            match = re.fullmatch(r"v(\d{4})", path.name)
            if match:
                version_numbers.append(int(match.group(1)))
        return f"v{(max(version_numbers, default=0) + 1):04d}"

    def _copy_raw_source(
        self,
        dataset_id: str,
        source_version_id: str,
        new_version_id: str,
    ) -> None:
        source_dir = settings.storage_root / "raw" / dataset_id / source_version_id
        target_dir = settings.storage_root / "raw" / dataset_id / new_version_id
        if source_dir.exists() and not target_dir.exists():
            shutil.copytree(source_dir, target_dir)

    def _preview_payload(self, dataframe: pd.DataFrame, limit: int) -> dict[str, Any]:
        preview = dataframe.head(max(1, min(limit, 100)))
        return {
            "columns": [str(column) for column in preview.columns],
            "rows": self._records(preview),
        }

    def _records(self, dataframe: pd.DataFrame) -> list[dict[str, Any]]:
        safe = dataframe.astype(object).where(pd.notnull(dataframe), None)
        return json.loads(safe.to_json(orient="records", date_format="iso", force_ascii=False))

    def _operation(
        self,
        operation_id: str,
        operation_type: str,
        target_column: str | None,
        parameters: dict[str, Any],
        rationale: str,
    ) -> dict[str, Any]:
        return {
            "id": operation_id,
            "operation_type": operation_type,
            "target_column": target_column,
            "parameters": parameters,
            "rationale": rationale,
            "enabled": True,
        }

    def _slug(self, value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
        return slug or str(abs(hash(value)))
