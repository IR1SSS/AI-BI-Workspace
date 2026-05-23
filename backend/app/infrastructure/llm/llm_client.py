from dataclasses import dataclass

import httpx

from app.infrastructure.settings import settings


@dataclass(frozen=True)
class LLMMessage:
    role: str
    content: str


class OpenAICompatibleClient:
    async def chat(self, messages: list[LLMMessage]) -> str:
        if not settings.llm_api_key:
            raise RuntimeError("LLM_API_KEY is not configured")

        if settings.llm_provider not in {"openai_compatible", "zhipu_glm"}:
            raise RuntimeError(f"Unsupported LLM provider: {settings.llm_provider}")

        payload = {
            "model": settings.llm_model,
            "messages": [message.__dict__ for message in messages],
        }
        headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
        async with httpx.AsyncClient(base_url=settings.llm_base_url, timeout=60) as client:
            response = await client.post("/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return str(data["choices"][0]["message"]["content"])
