import json
import re
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

BLOCKED_SQL_KEYWORDS = {
    "alter",
    "attach",
    "call",
    "copy",
    "create",
    "delete",
    "detach",
    "drop",
    "export",
    "import",
    "insert",
    "install",
    "load",
    "pragma",
    "update",
}


class DuckDBQueryEngine:
    def query_parquet(self, parquet_path: Path, sql: str, limit: int = 100) -> list[dict[str, Any]]:
        cleaned_sql = self._validate_read_only_sql(sql)
        limited_sql = f"SELECT * FROM ({cleaned_sql}) AS query_result LIMIT {limit}"

        connection = duckdb.connect(database=":memory:")
        try:
            escaped_path = str(parquet_path).replace("'", "''")
            connection.execute(
                f"CREATE VIEW dataset AS SELECT * FROM read_parquet('{escaped_path}')",
            )
            result = connection.execute(limited_sql).fetchdf()
            return self._records(result)
        finally:
            connection.close()

    def _validate_read_only_sql(self, sql: str) -> str:
        cleaned_sql = sql.strip().rstrip(";")
        lowered_sql = cleaned_sql.lower()
        if not lowered_sql.startswith(("select", "with")):
            raise ValueError("Only read-only SELECT queries are allowed")
        if ";" in cleaned_sql:
            raise ValueError("Multiple SQL statements are not allowed")
        for keyword in BLOCKED_SQL_KEYWORDS:
            if re.search(rf"\b{keyword}\b", lowered_sql):
                raise ValueError(f"SQL keyword is not allowed: {keyword}")
        return cleaned_sql

    def _records(self, dataframe: pd.DataFrame) -> list[dict[str, Any]]:
        safe = dataframe.astype(object).where(pd.notnull(dataframe), None)
        return json.loads(safe.to_json(orient="records", date_format="iso", force_ascii=False))
