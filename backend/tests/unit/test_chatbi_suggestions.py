import asyncio
import json

from app.infrastructure.chat.chatbi_service import ChatBIService


def _context() -> dict:
    return {
        "metadata": {"file_name": "regional_sales.csv"},
        "profile": {
            "row_count": 120,
            "column_count": 4,
            "columns": [
                {
                    "name": "地区",
                    "data_type": "string",
                    "is_numeric": False,
                    "is_datetime": False,
                    "unique_count": 6,
                    "sample_values": ["华东", "华南"],
                },
                {
                    "name": "销售额",
                    "data_type": "double",
                    "is_numeric": True,
                    "is_datetime": False,
                    "unique_count": 110,
                    "sample_values": [1200, 1800],
                },
                {
                    "name": "利润",
                    "data_type": "double",
                    "is_numeric": True,
                    "is_datetime": False,
                    "unique_count": 108,
                    "sample_values": [200, 360],
                },
                {
                    "name": "月份",
                    "data_type": "datetime",
                    "is_numeric": False,
                    "is_datetime": True,
                    "unique_count": 12,
                    "sample_values": ["2025-01"],
                },
            ],
            "quality_issues": [{"type": "missing_values", "column": "利润"}],
        },
        "analysis": {
            "insights": ["华东销售额较高"],
            "cleaning_suggestions": [],
            "feature_suggestions": [],
        },
        "sample_rows": [{"地区": "华东", "销售额": 1200, "利润": 200, "月份": "2025-01"}],
    }


def test_suggested_questions_uses_llm_context(monkeypatch):
    service = ChatBIService()
    captured = {}

    class FakeLLMClient:
        async def chat(self, messages):
            captured["prompt"] = messages[-1].content
            return json.dumps(
                {
                    "suggestions": [
                        "💡 哪个地区销售额最高？",
                        "📈 销售额按月份趋势如何？",
                        "🔍 利润缺失会影响哪些分析？",
                    ]
                },
                ensure_ascii=False,
            )

    service.llm_client = FakeLLMClient()
    monkeypatch.setattr(service, "_build_context", lambda _dataset_id, _version_id: _context())

    result = asyncio.run(service.suggested_questions("dataset-a", "v1"))

    assert result["source"] == "llm"
    assert result["suggestions"] == [
        "💡 哪个地区销售额最高？",
        "📈 销售额按月份趋势如何？",
        "🔍 利润缺失会影响哪些分析？",
    ]
    assert "销售额" in captured["prompt"]
    assert "地区" in captured["prompt"]


def test_suggested_questions_falls_back_from_profile(monkeypatch):
    service = ChatBIService()

    class FailingLLMClient:
        async def chat(self, _messages):
            raise RuntimeError("LLM unavailable")

    service.llm_client = FailingLLMClient()
    monkeypatch.setattr(service, "_build_context", lambda _dataset_id, _version_id: _context())

    result = asyncio.run(service.suggested_questions("dataset-a", "v1"))

    assert result["source"] == "profile_fallback"
    assert len(result["suggestions"]) == 3
    assert any("地区" in suggestion for suggestion in result["suggestions"])
    assert any("销售额" in suggestion for suggestion in result["suggestions"])
