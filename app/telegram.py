from httpx import AsyncClient

from app.config import Settings


class TelegramClient:
    def __init__(self, client: AsyncClient, settings: Settings) -> None:
        self._client = client
        self._token = settings.bot_token
        self._base = f"https://api.telegram.org/bot{self._token}"
        self._webhook_secret = settings.webhook_secret
        self._public_url = settings.public_url.rstrip("/")

    async def set_webhook(self) -> None:
        body = {
            "url": f"{self._public_url}/webhook",
            "secret_token": self._webhook_secret,
            "allowed_updates": ["message", "business_message", "business_connection"],
        }
        try:
            resp = await self._client.post(
                f"{self._base}/setWebhook",
                json=body,
            )
            resp.raise_for_status()
            result = resp.json()
            if not result.get("ok"):
                raise RuntimeError(f"setWebhook failed: {result}")
        except Exception:
            raise RuntimeError("failed to register webhook")

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_to_message_id: int | None = None,
        business_connection_id: str | None = None,
    ) -> None:
        body: dict = {
            "chat_id": chat_id,
            "text": text,
            "reply_to_message_id": reply_to_message_id,
        }
        if business_connection_id:
            body["business_connection_id"] = business_connection_id
        try:
            resp = await self._client.post(
                f"{self._base}/sendMessage",
                json=body,
            )
            resp.raise_for_status()
        except Exception:
            raise RuntimeError("failed to send message")
