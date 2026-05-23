from app.infrastructure.chat.chat_history_store import ChatHistoryStore
from app.infrastructure.settings import settings


def test_chat_history_store_persists_exchange(tmp_path):
    original_root = settings.storage_root
    settings.storage_root = tmp_path
    try:
        store = ChatHistoryStore()
        messages = store.append_exchange(
            "dataset-1",
            "v0001",
            "What is the average amount?",
            {
                "answer": "Average amount is 10.",
                "sql": "SELECT AVG(amount) FROM dataset",
                "rows": [{"avg": 10}],
                "source": "llm_sql",
                "error": "",
            },
        )

        loaded = store.list_messages("dataset-1", "v0001")
    finally:
        settings.storage_root = original_root

    assert len(messages) == 2
    assert loaded[0]["role"] == "user"
    assert loaded[1]["role"] == "assistant"
    assert loaded[1]["sql"] == "SELECT AVG(amount) FROM dataset"


def test_chat_history_store_deletes_messages(tmp_path):
    original_root = settings.storage_root
    settings.storage_root = tmp_path
    try:
        store = ChatHistoryStore()
        store.append_exchange("dataset-1", "v0001", "Question", {"answer": "Answer"})
        store.delete_messages("dataset-1", "v0001")
        loaded = store.list_messages("dataset-1", "v0001")
    finally:
        settings.storage_root = original_root

    assert loaded == []
