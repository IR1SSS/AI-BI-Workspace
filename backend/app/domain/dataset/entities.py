from dataclasses import dataclass


@dataclass(frozen=True)
class Dataset:
    id: str
    name: str
    current_version_id: str


@dataclass(frozen=True)
class DatasetVersion:
    id: str
    dataset_id: str
    parquet_path: str
    schema_path: str
    profile_path: str | None = None
