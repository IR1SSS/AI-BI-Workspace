from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.infrastructure.chat.chatbi_service import ChatBIService

router = APIRouter(prefix="/chat", tags=["chat"])


class DatasetChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1200)


@router.get("/datasets/{dataset_id}/versions/{version_id}/messages")
async def list_dataset_chat_messages(dataset_id: str, version_id: str) -> list[dict[str, Any]]:
    try:
        return ChatBIService().history(dataset_id, version_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/datasets/{dataset_id}/versions/{version_id}/suggestions")
async def list_dataset_chat_suggestions(dataset_id: str, version_id: str) -> dict[str, Any]:
    try:
        return await ChatBIService().suggested_questions(dataset_id, version_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/datasets/{dataset_id}/versions/{version_id}/messages")
async def chat_with_dataset(
    dataset_id: str,
    version_id: str,
    request: DatasetChatRequest,
) -> dict[str, Any]:
    try:
        return await ChatBIService().ask(dataset_id, version_id, request.question)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/datasets/{dataset_id}/versions/{version_id}/messages")
async def delete_dataset_chat_messages(dataset_id: str, version_id: str) -> dict[str, bool]:
    try:
        return ChatBIService().delete_history(dataset_id, version_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
