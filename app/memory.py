from datetime import datetime, timezone
from typing import Any

from httpx import AsyncClient

from app.config import Settings


class Memory:
    def __init__(self, client: AsyncClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings
        self._table = "quibo_conversations"
        self._base = f"{settings.supabase_url}/rest/v1"
        self._headers = {
            "apikey": settings.supabase_key,
            "Authorization": f"Bearer {settings.supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }

    async def get_history(self, chat_id: int, user_id: int, limit: int = 5) -> list[dict[str, Any]]:
        resp = await self._client.get(
            f"{self._base}/{self._table}",
            headers=self._headers,
            params={
                "chat_id": f"eq.{chat_id}",
                "user_id": f"eq.{user_id}",
                "order": "created_at.desc",
                "limit": limit,
            },
        )
        resp.raise_for_status()
        rows = resp.json()
        rows.reverse()
        return rows

    async def add_exchange(
        self, chat_id: int, user_id: int, prompt: str, reply: str
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            {"chat_id": chat_id, "user_id": user_id, "role": "user", "content": prompt, "created_at": now},
            {"chat_id": chat_id, "user_id": user_id, "role": "assistant", "content": reply, "created_at": now},
        ]
        resp = await self._client.post(
            f"{self._base}/{self._table}",
            headers=self._headers,
            json=rows,
        )
        resp.raise_for_status()

    async def cleanup_old(self, max_age_hours: int = 24) -> None:
        cutoff = datetime.now(timezone.utc).isoformat()
        resp = await self._client.delete(
            f"{self._base}/{self._table}",
            headers=self._headers,
            params={"created_at": f"lt.{cutoff}"},
        )
        resp.raise_for_status()
