from pathlib import Path
from typing import Any

import pandas as pd


class ParquetProfiler:
    def profile(self, dataset_version_id: str, parquet_path: Path) -> dict[str, Any]:
        dataframe = pd.read_parquet(parquet_path)
        columns = [self._profile_column(dataframe, column) for column in dataframe.columns]
        return {
            "dataset_version_id": dataset_version_id,
            "row_count": int(len(dataframe)),
            "column_count": int(len(dataframe.columns)),
            "columns": columns,
            "quality_issues": self._detect_quality_issues(dataframe, columns),
        }

    def _profile_column(self, dataframe: pd.DataFrame, column: str) -> dict[str, Any]:
        series = dataframe[column]
        non_null = series.dropna()
        row_count = max(int(len(dataframe)), 1)
        unique_count = int(series.nunique(dropna=True))
        null_count = int(series.isna().sum())
        sample_values = [self._json_value(value) for value in non_null.head(5).tolist()]
        return {
            "name": str(column),
            "data_type": str(series.dtype),
            "null_count": null_count,
            "null_ratio": round(null_count / row_count, 4),
            "unique_count": unique_count,
            "cardinality_ratio": round(unique_count / row_count, 4),
            "sample_values": sample_values,
            "is_numeric": bool(pd.api.types.is_numeric_dtype(series)),
            "is_datetime": bool(pd.api.types.is_datetime64_any_dtype(series)),
            "is_probable_index": str(column).lower().startswith("unnamed:"),
            "is_probable_identifier": self._is_probable_identifier(
                str(column),
                unique_count,
                row_count,
            ),
            "is_constant": unique_count <= 1,
        }

    def _detect_quality_issues(
        self,
        dataframe: pd.DataFrame,
        columns: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        duplicate_count = int(dataframe.duplicated().sum())
        if duplicate_count:
            issues.append(
                {
                    "type": "duplicate_rows",
                    "severity": "medium",
                    "column": None,
                    "count": duplicate_count,
                    "message": f"Dataset has {duplicate_count} duplicate row(s).",
                }
            )

        for column in columns:
            if column["is_probable_index"]:
                issues.append(
                    {
                        "type": "probable_index_column",
                        "severity": "medium",
                        "column": column["name"],
                        "count": 1,
                        "message": (
                            "Column looks like an exported dataframe index and can usually "
                            "be removed."
                        ),
                    }
                )
            if column["is_constant"]:
                issues.append(
                    {
                        "type": "constant_column",
                        "severity": "low",
                        "column": column["name"],
                        "count": column["unique_count"],
                        "message": (
                            "Column has one or fewer distinct values and adds little "
                            "analytical signal."
                        ),
                    }
                )
            if column["is_probable_identifier"] and not column["is_probable_index"]:
                issues.append(
                    {
                        "type": "probable_identifier",
                        "severity": "low",
                        "column": column["name"],
                        "count": column["unique_count"],
                        "message": (
                            "Column looks like an identifier and should not be used as a measure."
                        ),
                    }
                )
            if column["null_count"] > 0:
                severity = "high" if column["null_ratio"] >= 0.4 else "medium"
                issues.append(
                    {
                        "type": "missing_values",
                        "severity": severity,
                        "column": column["name"],
                        "count": column["null_count"],
                        "message": f"Column has {column['null_count']} missing values.",
                    }
                )

        return issues

    def _is_probable_identifier(self, column_name: str, unique_count: int, row_count: int) -> bool:
        lowered = column_name.lower()
        if any(token in lowered for token in ["id", "编号", "单号", "编码", "code", "sku"]):
            return True
        return row_count >= 10 and unique_count >= int(row_count * 0.9)

    def _json_value(self, value: Any) -> Any:
        if pd.isna(value):
            return None
        if hasattr(value, "item"):
            return value.item()
        return str(value) if not isinstance(value, int | float | bool | str) else value
