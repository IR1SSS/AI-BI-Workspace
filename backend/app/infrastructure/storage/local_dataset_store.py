import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
from fastapi import UploadFile
from pandas.api import types as pandas_types

from app.domain.dataset.entities import Dataset
from app.infrastructure.analysis.ai_analysis_planner import AIAnalysisPlanner
from app.infrastructure.catalog.dataset_catalog import DatasetCatalog
from app.infrastructure.profiling.parquet_profiler import ParquetProfiler
from app.infrastructure.settings import settings
from app.infrastructure.visualization.dashboard_generator import DashboardGenerator


class LocalDatasetStore:
    def __init__(self) -> None:
        self.catalog = DatasetCatalog()
        self.profiler = ParquetProfiler()
        self.dashboard_generator = DashboardGenerator()
        self.analysis_planner = AIAnalysisPlanner()

    async def save_uploaded_file(self, file: UploadFile) -> Dataset:
        original_name = file.filename or "source.csv"
        return await self.save_local_file(file.file, original_name)

    async def save_local_file(self, file_object: Any, original_name: str) -> Dataset:
        dataset_id = str(uuid4())
        version_id = "v0001"
        dataset_dir = settings.storage_root / "raw" / dataset_id / version_id
        warehouse_dir = settings.storage_root / "warehouse" / dataset_id / version_id
        dataset_dir.mkdir(parents=True, exist_ok=True)
        warehouse_dir.mkdir(parents=True, exist_ok=True)

        suffix = Path(original_name).suffix.lower()
        source_path = dataset_dir / f"source{suffix}"
        with source_path.open("wb") as target:
            shutil.copyfileobj(file_object, target)

        parquet_path = warehouse_dir / "data.parquet"
        try:
            self._convert_to_parquet(source_path, parquet_path)
            dataframe = pd.read_parquet(parquet_path)
            profile = self.profiler.profile(version_id, parquet_path)
            analysis = await self.analysis_planner.plan(profile)
            dashboard = self.dashboard_generator.generate(
                dataset_id,
                version_id,
                original_name,
                profile,
                dataframe,
                analysis,
            )
            metadata = {
                "dataset_id": dataset_id,
                "version_id": version_id,
                "file_name": original_name,
                "raw_path": str(source_path),
                "parquet_path": str(parquet_path),
                "created_at": datetime.now(UTC).isoformat(),
                "row_count": profile["row_count"],
                "column_count": profile["column_count"],
                "profile_status": "ready",
                "dashboard_status": "ready",
            }
            self.catalog.write_dataset_artifacts(
                dataset_id,
                version_id,
                metadata,
                profile,
                dashboard,
                analysis,
            )
            return Dataset(id=dataset_id, name=original_name, current_version_id=version_id)
        except Exception:
            shutil.rmtree(dataset_dir, ignore_errors=True)
            shutil.rmtree(warehouse_dir, ignore_errors=True)
            raise

    def _convert_to_parquet(self, source_path: Path, parquet_path: Path) -> None:
        suffix = source_path.suffix.lower()
        if suffix == ".csv":
            dataframe = pd.read_csv(source_path)
            dataframe = self._normalize_dataframe_for_parquet(dataframe)
            dataframe.to_parquet(parquet_path, index=False)
            return

        if suffix in {".json", ".jsonl"}:
            dataframe = pd.read_json(source_path, lines=suffix == ".jsonl")
            dataframe = self._normalize_dataframe_for_parquet(dataframe)
            dataframe.to_parquet(parquet_path, index=False)
            return

        if suffix in {".xls", ".xlsx"}:
            dataframe = pd.read_excel(source_path)
            dataframe = self._normalize_dataframe_for_parquet(dataframe)
            dataframe.to_parquet(parquet_path, index=False)
            return

        raise ValueError(f"Unsupported file type for initial import: {suffix}")

    def _normalize_dataframe_for_parquet(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        normalized = dataframe.copy()
        normalized.columns = self._unique_column_names(
            [str(column) for column in normalized.columns]
        )
        for column in normalized.columns:
            if pandas_types.is_object_dtype(normalized[column]):
                normalized[column] = normalized[column].map(self._normalize_object_cell)
        return self._append_derived_features(normalized)

    def _append_derived_features(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        enriched = dataframe.copy()
        for column in list(enriched.columns):
            if not pandas_types.is_object_dtype(enriched[column]):
                continue

            if self._looks_temporal_column(column):
                years = enriched[column].map(self._parse_year_like)
                if self._has_enough_derived_values(years, enriched[column]):
                    year_column = self._next_unique_column_name(
                        enriched.columns.tolist(),
                        f"{column}_年份",
                    )
                    enriched[year_column] = pd.Series(years, dtype="Int64")
                continue

            if self._looks_identifier_or_free_text(column):
                continue

            numeric_values = enriched[column].map(self._parse_numeric_like)
            if self._has_enough_derived_values(numeric_values, enriched[column]):
                numeric_column = self._next_unique_column_name(
                    enriched.columns.tolist(),
                    f"{column}_数值",
                )
                enriched[numeric_column] = pd.to_numeric(numeric_values, errors="coerce")
        return self._append_datetime_delta_features(enriched)

    def _append_datetime_delta_features(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        enriched = dataframe.copy()
        temporal_columns = [
            column
            for column in enriched.columns
            if pandas_types.is_datetime64_any_dtype(enriched[column])
            or self._looks_temporal_column(str(column))
        ]
        if len(temporal_columns) < 2:
            return enriched

        for start_column, end_column in self._datetime_delta_pairs(temporal_columns):
            start_values = pd.to_datetime(enriched[start_column], errors="coerce")
            end_values = pd.to_datetime(enriched[end_column], errors="coerce")
            delta_days = (end_values - start_values).dt.days
            if not self._has_enough_derived_values(delta_days, enriched[end_column]):
                continue
            if delta_days.dropna().nunique() <= 1:
                continue
            preferred = f"{end_column}_较_{start_column}_天数"
            delta_column = self._next_unique_column_name(enriched.columns.tolist(), preferred)
            enriched[delta_column] = delta_days
        return enriched

    def _datetime_delta_pairs(self, temporal_columns: list[str]) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        planned = [column for column in temporal_columns if self._looks_planned_time_column(column)]
        actual = [column for column in temporal_columns if self._looks_actual_time_column(column)]
        for planned_column in planned:
            for actual_column in actual:
                if planned_column != actual_column:
                    pairs.append((planned_column, actual_column))
        if pairs:
            return pairs[:2]
        return [(temporal_columns[0], temporal_columns[1])]

    def _normalize_object_cell(self, value: Any) -> str | None:
        if pd.isna(value):
            return None
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
        return str(value)

    def _parse_numeric_like(self, value: Any) -> float | None:
        if pd.isna(value):
            return None
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)

        text = str(value).strip()
        if not text:
            return None

        multiplier = 1.0
        if "亿" in text:
            multiplier = 100_000_000.0
        elif "万" in text:
            multiplier = 10_000.0
        elif "%" in text:
            multiplier = 0.01

        normalized = (
            text.replace(",", "")
            .replace("，", "")
            .replace("￥", "")
            .replace("¥", "")
            .replace("$", "")
            .replace("元", "")
            .replace("票房", "")
            .replace("约", "")
            .replace(" ", "")
        )
        match = re.search(r"[-+]?\d+(?:\.\d+)?", normalized)
        if not match:
            return None
        return float(match.group(0)) * multiplier

    def _parse_year_like(self, value: Any) -> int | None:
        if pd.isna(value):
            return None
        text = str(value).strip()
        if not text:
            return None
        match = re.search(r"(19|20)\d{2}", text)
        if not match:
            return None
        return int(match.group(0))

    def _has_enough_derived_values(self, derived: pd.Series, source: pd.Series) -> bool:
        non_null_count = int(source.dropna().shape[0])
        if non_null_count == 0:
            return False
        derived_count = int(pd.Series(derived).dropna().shape[0])
        return derived_count >= max(3, int(non_null_count * 0.4))

    def _looks_temporal_column(self, column: str) -> bool:
        lowered = column.lower()
        return any(token in lowered for token in ["date", "time", "year", "日期", "时间", "年份"])

    def _looks_planned_time_column(self, column: str) -> bool:
        lowered = column.lower()
        tokens = ["plan", "planned", "target", "计划", "预计", "应"]
        return any(token in lowered for token in tokens)

    def _looks_actual_time_column(self, column: str) -> bool:
        lowered = column.lower()
        tokens = ["actual", "real", "completed", "实际", "真实", "完成"]
        return any(token in lowered for token in tokens)

    def _looks_identifier_or_free_text(self, column: str) -> bool:
        lowered = column.lower()
        blocked_tokens = [
            "id",
            "url",
            "link",
            "链接",
            "网址",
            "编号",
            "单号",
            "订单号",
            "采购订单",
            "订单编号",
            "单据",
            "凭证",
            "流水号",
            "编码",
            "代码",
            "sku",
            "serial",
            "barcode",
            "code",
            "名称",
            "名字",
            "姓名",
            "电影名",
            "标题",
            "title",
            "name",
        ]
        return any(token in lowered for token in blocked_tokens)

    def _next_unique_column_name(self, existing_columns: list[str], preferred: str) -> str:
        existing = set(existing_columns)
        if preferred not in existing:
            return preferred
        index = 2
        while f"{preferred}_{index}" in existing:
            index += 1
        return f"{preferred}_{index}"

    def _unique_column_names(self, columns: list[str]) -> list[str]:
        seen: dict[str, int] = {}
        result: list[str] = []
        for column in columns:
            clean_column = column.strip() or "column"
            count = seen.get(clean_column, 0)
            seen[clean_column] = count + 1
            result.append(clean_column if count == 0 else f"{clean_column}_{count + 1}")
        return result
