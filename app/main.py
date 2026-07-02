import logging
import re
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request

from app.config import Settings
from app.llm import LLMClient
from app.memory import Memory
from app.rate_limiter import RateLimiter
from app.telegram import TelegramClient

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
        yield


app = FastAPI(lifespan=lifespan)

BOT_MENTION_RE = re.compile(r"@quibo_ai_bot\s*", re.IGNORECASE)


def _extract_prompt(text: str) -> str | None:
    text = text.strip()
    prompt = BOT_MENTION_RE.sub("", text, count=1).strip()
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

    msg = update.get("message")
    if not msg:
        return {"ok": True}

    chat = msg.get("chat", {})
    chat_type = chat.get("type", "")
    if chat_type == "private":
        return {"ok": True}

    text = msg.get("text", "")
    if not text:
        return {"ok": True}

    prompt = _extract_prompt(text)
    chat_id = chat["id"]
    user = msg.get("from", {})
    user_id = user.get("id", 0)

    if prompt is None:
        hint = "Hi, I'm Quibo! Mention me with a question to get started."
        await app.state.telegram.send_message(
            chat_id=chat_id,
            text=hint,
            reply_to_message_id=msg["message_id"],
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
        )

        await app.state.memory.cleanup_old()

        elapsed = time.monotonic() - start
        logger.info(
            "mention | chat_id=%d user_id=%d prompt_len=%d response_len=%d latency=%.2fs",
            chat_id, user_id, len(prompt), len(reply), elapsed,
        )
    except Exception:
        logger.exception("error handling mention | chat_id=%d user_id=%d", chat_id, user_id)

    return {"ok": True}
