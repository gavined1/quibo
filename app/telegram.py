from httpx import AsyncClient

from app.config import Settings


class TelegramClient:
    def __init__(self, client: AsyncClient, settings: Settings) -> None:
        self._client = client
        self._base = f"https://api.telegram.org/bot{settings.bot_token}"

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_to_message_id: int | None = None,
    ) -> None:
        body = {
            "chat_id": chat_id,
            "text": text,
            "reply_to_message_id": reply_to_message_id,
        }
        resp = await self._client.post(
            f"{self._base}/sendMessage",
            json=body,
        )
        resp.raise_for_status()
