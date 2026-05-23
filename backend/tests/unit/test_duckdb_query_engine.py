import pandas as pd
import pytest
from app.infrastructure.query.duckdb_query_engine import DuckDBQueryEngine


def test_query_parquet_allows_read_only_select(tmp_path):
    parquet_path = tmp_path / "sample.parquet"
    pd.DataFrame({"category": ["a", "a", "b"], "amount": [10, 20, 5]}).to_parquet(parquet_path)

    rows = DuckDBQueryEngine().query_parquet(
        parquet_path,
        'SELECT "category", SUM("amount") AS total '
        'FROM dataset GROUP BY "category" ORDER BY total DESC',
    )

    assert rows == [{"category": "a", "total": 30}, {"category": "b", "total": 5}]


def test_query_parquet_blocks_non_select_statements(tmp_path):
    parquet_path = tmp_path / "sample.parquet"
    pd.DataFrame({"amount": [10]}).to_parquet(parquet_path)

    with pytest.raises(ValueError, match="Only read-only SELECT queries are allowed"):
        DuckDBQueryEngine().query_parquet(parquet_path, "DROP TABLE dataset")


def test_query_parquet_blocks_dangerous_keywords_in_cte(tmp_path):
    parquet_path = tmp_path / "sample.parquet"
    pd.DataFrame({"amount": [10]}).to_parquet(parquet_path)

    with pytest.raises(ValueError, match="SQL keyword is not allowed"):
        DuckDBQueryEngine().query_parquet(parquet_path, "WITH x AS (SELECT 1) DELETE FROM dataset")
