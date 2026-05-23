from fastapi import UploadFile

from app.domain.dataset.entities import Dataset
from app.infrastructure.storage.storage_contracts import DatasetStore


class ImportFileDataset:
    def __init__(self, dataset_store: DatasetStore) -> None:
        self.dataset_store = dataset_store

    async def execute(self, file: UploadFile) -> Dataset:
        return await self.dataset_store.save_uploaded_file(file)
