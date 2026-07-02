import asyncio
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel
from pydantic_settings import BaseSettings

# =====================
# CONFIG
# =====================
class Settings(BaseSettings):
    BOT_TOKEN: str
    WEBHOOK_SECRET: str

    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_API_KEY: str
    LLM_MODEL: str = "gpt-4o-mini"

    SUPABASE_URL: str
    SUPABASE_KEY: str

    RATE_LIMIT_PER_MINUTE: int = 5

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()

# =====================
# LOGGING
# =====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("quibo")

# =====================
# RATE LIMITING (in-memory)
# =====================
rate_limits: dict[int, list[float]] = {}
rate_limit_lock = asyncio.Lock()


async def check_rate_limit(user_id: int) -> bool:
    """Return True if allowed, False if rate limited."""
    async with rate_limit_lock:
        now = time.time()
        window_start = now - 60

        if user_id not in rate_limits:
            rate_limits[user_id] = []

        rate_limits[user_id] = [ts for ts in rate_limits[user_id] if ts > window_start]

        if len(rate_limits[user_id]) >= settings.RATE_LIMIT_PER_MINUTE:
            return False

        rate_limits[user_id].append(now)
        return True


# =====================
# SUPABASE (REST)
# =====================
SUPABASE_HEADERS = {
    "apikey": settings.SUPABASE_KEY,
    "Authorization": f"Bearer {settings.SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}


async def supabase_insert(chat_id: int, user_id: int, role: str, content: str) -> None:
    url = f"{settings.SUPABASE_URL}/rest/v1/quibo_conversations"
    payload = {
        "chat_id": chat_id,
        "user_id": user_id,
        "role": role,
        "content": content,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    resp = await httpx_client.post(url, json=payload, headers=SUPABASE_HEADERS)
    if resp.status_code >= 400:
        logger.error(f"Supabase insert failed: {resp.status_code} {resp.text}")
    resp.close()


async def supabase_get_recent(chat_id: int, user_id: int, limit: int = 10) -> list[dict]:
    url = (
        f"{settings.SUPABASE_URL}/rest/v1/quibo_conversations"
        f"?select=role,content,created_at"
        f"&chat_id=eq.{chat_id}"
        f"&user_id=eq.{user_id}"
        f"&order=created_at.desc"
        f"&limit={limit}"
    )

    resp = await httpx_client.get(url, headers=SUPABASE_HEADERS)
    if resp.status_code >= 400:
        logger.error(f"Supabase fetch failed: {resp.status_code} {resp.text}")
        resp.close()
        return []
    data = resp.json()
    resp.close()
    return data


async def supabase_cleanup_old(chat_id: int, user_id: int) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    url = (
        f"{settings.SUPABASE_URL}/rest/v1/quibo_conversations"
        f"?chat_id=eq.{chat_id}"
        f"&user_id=eq.{user_id}"
        f"&created_at=lt.{cutoff}"
    )

    resp = await httpx_client.delete(url, headers=SUPABASE_HEADERS)
    if resp.status_code >= 400:
        logger.warning(f"Supabase cleanup failed: {resp.status_code} {resp.text}")
    resp.close()


# =====================
# LLM
# =====================
async def call_llm(history: list[dict], user_prompt: str) -> str:
    system_prompt = (
        "You are Quibo, a helpful AI assistant. "
        "Keep every response concise and under 500 characters. "
        "Be direct, clear, and useful. Do not add unnecessary pleasantries."
    )

    messages = [{"role": "system", "content": system_prompt}]

    for msg in reversed(history):
        messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": user_prompt})

    url = f"{settings.LLM_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.LLM_MODEL,
        "messages": messages,
        "max_tokens": 300,
        "temperature": 0.7,
    }

    start = time.time()
    try:
        resp = await httpx_client.post(url, json=payload, headers=headers, timeout=30.0)
        latency = time.time() - start

        if resp.status_code >= 400:
            error_text = resp.text
            logger.error(f"LLM error {resp.status_code}: {error_text}")
            resp.close()
            return "Sorry, I had trouble generating a response right now."

        data = resp.json()
        resp.close()

        content = data["choices"][0]["message"]["content"].strip()
        if len(content) > 500:
            content = content[:497] + "..."

        logger.info(f"LLM response generated in {latency:.2f}s (len={len(content)})")
        return content
    except Exception as e:
        logger.exception(f"LLM call failed: {e}")
        return "Sorry, something went wrong while thinking about your question."


# =====================
# TELEGRAM
# =====================
TELEGRAM_API = "https://api.telegram.org"


async def send_telegram_reply(chat_id: int, reply_to_message_id: int, text: str) -> None:
    url = f"{TELEGRAM_API}/bot{settings.BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "reply_to_message_id": reply_to_message_id,
    }

    try:
        resp = await httpx_client.post(url, json=payload, timeout=10.0)
        if resp.status_code >= 400:
            logger.error(f"Telegram sendMessage failed: {resp.status_code} {resp.text}")
        resp.close()
    except Exception as e:
        logger.exception(f"Failed to send Telegram reply: {e}")


def extract_prompt_from_mention(text: str, entities: list[dict] | None) -> Optional[str]:
    if not text:
        return None

    bot_mention = "@quibo_ai_bot"
    lower_text = text.lower()

    if entities:
        for ent in entities:
            if ent.get("type") == "mention":
                mention = text[ent["offset"] : ent["offset"] + ent["length"]]
                if mention.lower() == bot_mention:
                    after = text[ent["offset"] + ent["length"] :].strip()
                    return after if after else ""

    if bot_mention in lower_text:
        idx = lower_text.find(bot_mention)
        after = text[idx + len(bot_mention) :].strip()
        return after if after else ""

    return None


async def handle_mention(update: dict) -> None:
    message = update.get("message")
    if not message or "text" not in message:
        return

    chat = message.get("chat", {})
    chat_type = chat.get("type", "")
    chat_id = chat.get("id")

    if chat_type not in ("group", "supergroup"):
        return

    from_user = message.get("from", {})
    user_id = from_user.get("id")
    if not user_id:
        return

    text = message.get("text", "")
    entities = message.get("entities", [])
    message_id = message.get("message_id")

    prompt = extract_prompt_from_mention(text, entities)

    if prompt is None:
        return

    if not prompt:
        await send_telegram_reply(
            chat_id, message_id, "Hi, I'm Quibo! Mention me with a question to get started."
        )
        return

    allowed = await check_rate_limit(user_id)
    if not allowed:
        logger.info(f"Rate limited user {user_id} in chat {chat_id}")
        return

    logger.info(f"Processing mention | chat_id={chat_id} user_id={user_id} prompt={prompt[:100]!r}")

    start_time = time.time()

    await supabase_cleanup_old(chat_id, user_id)
    recent = await supabase_get_recent(chat_id, user_id, limit=10)

    response_text = await call_llm(recent, prompt)

    await send_telegram_reply(chat_id, message_id, response_text)

    await supabase_insert(chat_id, user_id, "user", prompt)
    await supabase_insert(chat_id, user_id, "assistant", response_text)

    latency = time.time() - start_time
    logger.info(
        f"Mention handled | chat_id={chat_id} user_id={user_id} "
        f"prompt_len={len(prompt)} response_len={len(response_text)} latency={latency:.2f}s"
    )


# =====================
# FASTAPI
# =====================
@asynccontextmanager
async def lifespan(app: FastAPI):
    global httpx_client
    httpx_client = httpx.AsyncClient(
        limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
        timeout=httpx.Timeout(30.0),
    )
    logger.info("Quibo bot started")
    yield
    await httpx_client.aclose()
    logger.info("Quibo bot shutdown")


app = FastAPI(title="Quibo", lifespan=lifespan)
httpx_client: httpx.AsyncClient


class TelegramUpdate(BaseModel):
    update_id: int
    message: Optional[dict] = None


@app.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: Optional[str] = Header(None),
):
    if x_telegram_bot_api_secret_token != settings.WEBHOOK_SECRET:
        logger.warning("Invalid webhook secret token")
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Only process new messages (not edits)
    if payload.get("message"):
        await handle_mention(payload)

    return {"ok": True}


@app.get("/")
async def health():
    return {"status": "ok", "bot": "quibo"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)