from typing import Protocol

from fastapi import UploadFile

from app.domain.dataset.entities import Dataset


class DatasetStore(Protocol):
    async def save_uploaded_file(self, file: UploadFile) -> Dataset:
        pass
