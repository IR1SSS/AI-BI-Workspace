import pandas as pd
from app.infrastructure.storage.local_dataset_store import LocalDatasetStore


def test_normalize_dataframe_for_parquet_converts_mixed_object_columns():
    release_time = "\u4e0a\u6620\u65f6\u95f4"
    dataframe = pd.DataFrame(
        {
            release_time: ["2024-01-01", 20240501, None],
            "score": [8.2, 7.4, 9.1],
            "": ["a", "b", "c"],
        }
    )

    normalized = LocalDatasetStore()._normalize_dataframe_for_parquet(dataframe)

    assert normalized.columns.tolist() == [release_time, "score", "column"]
    assert normalized[release_time].tolist() == ["2024-01-01", "20240501", None]
    assert normalized["score"].tolist() == [8.2, 7.4, 9.1]


def test_normalize_dataframe_for_parquet_adds_numeric_and_year_features():
    box_office = "\u7d2f\u8ba1\u7968\u623f"
    release_time = "\u4e0a\u6620\u65f6\u95f4"
    link = "\u94fe\u63a5"
    dataframe = pd.DataFrame(
        {
            box_office: ["1.2\u4ebf", "3500\u4e07", "985,000", "\u6682\u65e0", "2\u4ebf"],
            release_time: ["2024-01-01", "2023/05/20", "2022", "2021-11", None],
            link: ["https://a/1", "https://a/2", "https://a/3", "https://a/4", "https://a/5"],
        }
    )

    normalized = LocalDatasetStore()._normalize_dataframe_for_parquet(dataframe)

    assert f"{box_office}_\u6570\u503c" in normalized.columns
    assert f"{release_time}_\u5e74\u4efd" in normalized.columns
    assert f"{link}_\u6570\u503c" not in normalized.columns
    assert normalized[f"{box_office}_\u6570\u503c"].dropna().tolist() == [
        120_000_000.0,
        35_000_000.0,
        985_000.0,
        200_000_000.0,
    ]
    assert normalized[f"{release_time}_\u5e74\u4efd"].dropna().tolist() == [2024, 2023, 2022, 2021]


def test_normalize_dataframe_for_parquet_derives_delivery_delta_and_skips_order_id():
    order_id = "\u91c7\u8d2d\u8ba2\u5355\u53f7"
    planned = "\u8ba1\u5212\u4ea4\u8d27\u65e5\u671f"
    actual = "\u5b9e\u9645\u4ea4\u8d27\u65e5\u671f"
    dataframe = pd.DataFrame(
        {
            order_id: ["4500366357", "4700008856", "4500366356"],
            planned: pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01"]),
            actual: pd.to_datetime(["2024-01-03", "2024-01-30", "2024-03-08"]),
        }
    )

    normalized = LocalDatasetStore()._normalize_dataframe_for_parquet(dataframe)

    assert f"{order_id}_\u6570\u503c" not in normalized.columns
    delta_column = f"{actual}_\u8f83_{planned}_\u5929\u6570"
    assert delta_column in normalized.columns
    assert normalized[delta_column].tolist() == [2, -2, 7]
