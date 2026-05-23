import pandas as pd
from app.infrastructure.profiling.parquet_profiler import ParquetProfiler


def test_profiler_detects_richer_quality_issues(tmp_path):
    parquet_path = tmp_path / "sample.parquet"
    dataframe = pd.DataFrame(
        {
            "order_id": [f"o-{index}" for index in range(10)] + ["o-9"],
            "constant": ["same"] * 11,
            "mostly_missing": [None, None, None, None, None, "x", "x", "y", "z", "z", "z"],
            "amount": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10],
        }
    )
    dataframe.to_parquet(parquet_path, index=False)

    profile = ParquetProfiler().profile("v0001", parquet_path)

    issue_types = {issue["type"] for issue in profile["quality_issues"]}
    order_id = next(column for column in profile["columns"] if column["name"] == "order_id")
    mostly_missing = next(
        column for column in profile["columns"] if column["name"] == "mostly_missing"
    )

    assert issue_types >= {
        "constant_column",
        "missing_values",
        "probable_identifier",
    }
    assert order_id["is_probable_identifier"] is True
    assert mostly_missing["null_ratio"] > 0.4


def test_profiler_detects_duplicate_rows(tmp_path):
    parquet_path = tmp_path / "sample.parquet"
    pd.DataFrame({"category": ["a", "a", "b"], "amount": [10, 10, 20]}).to_parquet(
        parquet_path,
        index=False,
    )

    profile = ParquetProfiler().profile("v0001", parquet_path)

    duplicate_issue = next(
        issue for issue in profile["quality_issues"] if issue["type"] == "duplicate_rows"
    )
    assert duplicate_issue["count"] == 1
