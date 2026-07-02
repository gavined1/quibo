from httpx import AsyncClient

from app.config import Settings


class LLMClient:
    def __init__(self, client: AsyncClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    async def complete(self, messages: list[dict[str, str]]) -> str:
        body = {
            "model": self._settings.llm_model,
            "messages": messages,
            "max_tokens": 300,
        }
        resp = await self._client.post(
            f"{self._settings.llm_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._settings.llm_api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
