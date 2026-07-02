import logging
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request

from app.config import Settings
from app.llm import LLMClient
from app.memory import Memory
from app.rate_limiter import RateLimiter
from app.telegram import TelegramClient

logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("quibo")
logging.basicConfig(level=logging.INFO, format="%(levelname)-5s | %(message)s")

settings = Settings()

rate_limiter = RateLimiter(max_requests=settings.rate_limit_max, window=settings.rate_limit_window)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as http_client:
        _app.state.http = http_client
        _app.state.telegram = TelegramClient(http_client, settings)
        _app.state.llm = LLMClient(http_client, settings)
        _app.state.memory = Memory(http_client, settings)
        await _app.state.telegram.set_webhook()
        logger.info("webhook registered at %s/webhook", settings.public_url.rstrip("/"))
        yield


app = FastAPI(lifespan=lifespan)

HINT = "Hi, I'm Quibo! Type @ai followed by your question to get started."


def _extract_prompt(text: str) -> str | None:
    text = text.strip()
    idx = text.lower().find("@ai")
    if idx == -1:
        return None
    prompt = text[idx + 3:].strip()
    if not prompt:
        return None
    return prompt


def _build_messages(history: list[dict], prompt: str) -> list[dict[str, str]]:
    system = {"role": "system", "content": "You are Quibo, a helpful Telegram bot. Keep responses concise and under 500 characters."}
    messages: list[dict[str, str]] = [system]
    for row in history:
        messages.append({"role": row["role"], "content": row["content"]})
    messages.append({"role": "user", "content": prompt})
    return messages


@app.post("/webhook")
async def webhook(request: Request) -> dict:
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret != settings.webhook_secret:
        raise HTTPException(status_code=403, detail="Invalid secret")

    body = await request.json()
    update = body

    msg = update.get("business_message") or update.get("message")
    if not msg:
        logger.info("ignored (no business_message/message) | keys=%s", list(update.keys()))
        return {"ok": True}

    text = msg.get("text", "")
    if not text:
        return {"ok": True}

    if "@ai" not in text.lower():
        return {"ok": True}

    prompt = _extract_prompt(text)
    chat = msg.get("chat", {})
    chat_id = chat["id"]
    user = msg.get("from", {})
    user_id = user.get("id", 0)
    business_connection_id = msg.get("business_connection_id")

    if prompt is None:
        await app.state.telegram.send_message(
            chat_id=chat_id,
            text=HINT,
            reply_to_message_id=msg["message_id"],
            business_connection_id=business_connection_id,
        )
        return {"ok": True}

    if not rate_limiter.check(user_id):
        logger.warning("rate_limit | user_id=%d chat_id=%d", user_id, chat_id)
        return {"ok": True}

    rate_limiter.record(user_id)

    start = time.monotonic()

    try:
        history = await app.state.memory.get_history(chat_id, user_id)
        messages = _build_messages(history, prompt)
        reply = await app.state.llm.complete(messages)

        if len(reply) > 500:
            reply = reply[:497] + "..."

        await app.state.memory.add_exchange(chat_id, user_id, prompt, reply)

        await app.state.telegram.send_message(
            chat_id=chat_id,
            text=reply,
            reply_to_message_id=msg["message_id"],
            business_connection_id=business_connection_id,
        )

        await app.state.memory.cleanup_old()

        elapsed = time.monotonic() - start
        logger.info(
            "trigger | chat_id=%d user_id=%d prompt_len=%d response_len=%d latency=%.2fs",
            chat_id, user_id, len(prompt), len(reply), elapsed,
        )
    except Exception:
        logger.exception("error handling trigger | chat_id=%d user_id=%d", chat_id, user_id)

    return {"ok": True}
