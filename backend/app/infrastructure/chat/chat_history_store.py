import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.infrastructure.settings import settings


class ChatHistoryStore:
    def list_messages(self, dataset_id: str, version_id: str) -> list[dict[str, Any]]:
        path = self._history_path(dataset_id, version_id)
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            return []
        return [message for message in payload if isinstance(message, dict)]

    def append_exchange(
        self,
        dataset_id: str,
        version_id: str,
        question: str,
        response: dict[str, Any],
    ) -> list[dict[str, Any]]:
        messages = self.list_messages(dataset_id, version_id)
        messages.append(self._message("user", question))
        messages.append(
            self._message(
                "assistant",
                str(response.get("answer") or ""),
                {
                    "sql": response.get("sql") or "",
                    "rows": response.get("rows") or [],
                    "source": response.get("source") or "",
                    "error": response.get("error") or "",
                },
            )
        )
        self._write_messages(dataset_id, version_id, messages)
        return messages

    def delete_messages(self, dataset_id: str, version_id: str) -> None:
        path = self._history_path(dataset_id, version_id)
        if path.exists():
            path.unlink()

    def _message(
        self,
        role: str,
        content: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        message = {
            "id": str(uuid4()),
            "role": role,
            "content": content,
            "created_at": datetime.now(UTC).isoformat(),
        }
        if extra:
            message.update(extra)
        return message

    def _write_messages(
        self,
        dataset_id: str,
        version_id: str,
        messages: list[dict[str, Any]],
    ) -> None:
        path = self._history_path(dataset_id, version_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8")

    def _history_path(self, dataset_id: str, version_id: str) -> Path:
        return settings.storage_root / "warehouse" / dataset_id / version_id / "chat_messages.json"
