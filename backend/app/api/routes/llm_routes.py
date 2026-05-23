import time
from typing import Any

from fastapi import APIRouter

from app.infrastructure.llm.llm_client import LLMMessage, OpenAICompatibleClient
from app.infrastructure.settings import settings

router = APIRouter(prefix="/llm", tags=["llm"])


@router.get("/config")
async def get_llm_config() -> dict[str, str | bool]:
    return {
        "provider": settings.llm_provider,
        "base_url": settings.llm_base_url,
        "model": settings.llm_model,
        "api_key_configured": bool(settings.llm_api_key),
    }


@router.get("/health")
async def get_llm_health() -> dict[str, Any]:
    started_at = time.perf_counter()
    if not settings.llm_api_key:
        return _health_payload("error", "LLM_API_KEY is not configured", started_at)

    try:
        content = await OpenAICompatibleClient().chat(
            [
                LLMMessage(
                    role="user",
                    content="Reply with exactly: ok",
                )
            ]
        )
    except Exception as exc:
        return _health_payload("error", str(exc), started_at)

    return _health_payload("ok", "", started_at, content.strip()[:80])


def _health_payload(
    status: str,
    error: str,
    started_at: float,
    sample: str = "",
) -> dict[str, Any]:
    return {
        "status": status,
        "provider": settings.llm_provider,
        "base_url": settings.llm_base_url,
        "model": settings.llm_model,
        "api_key_configured": bool(settings.llm_api_key),
        "latency_ms": round((time.perf_counter() - started_at) * 1000),
        "sample": sample,
        "error": error,
    }
