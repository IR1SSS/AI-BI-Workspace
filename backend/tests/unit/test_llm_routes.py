import asyncio

from app.api.routes import llm_routes
from app.infrastructure.settings import settings


def test_llm_health_reports_missing_key():
    original_key = settings.llm_api_key
    settings.llm_api_key = ""
    try:
        result = asyncio.run(llm_routes.get_llm_health())
    finally:
        settings.llm_api_key = original_key

    assert result["status"] == "error"
    assert result["api_key_configured"] is False
    assert "LLM_API_KEY" in result["error"]


def test_llm_health_uses_client(monkeypatch):
    class FakeClient:
        async def chat(self, messages):
            assert messages[0].content == "Reply with exactly: ok"
            return "ok"

    monkeypatch.setattr(llm_routes, "OpenAICompatibleClient", FakeClient)

    original_key = settings.llm_api_key
    settings.llm_api_key = "test-key"
    try:
        result = asyncio.run(llm_routes.get_llm_health())
    finally:
        settings.llm_api_key = original_key

    assert result["status"] == "ok"
    assert result["sample"] == "ok"
