# Quibo — Telegram Bot

A FastAPI-based Telegram bot that triggers on the keyword `@ai` in any chat using Telegram's **Chat Automation** (Business Connection) feature. Backed by an OpenAI-compatible LLM and Supabase for conversation memory.

## How it works

- Users connect the bot via **Settings > Chat Automation** and set up a keyword trigger for `@ai`.
- When `@ai` appears anywhere in a message, Telegram sends a `business_message` update to the bot's webhook.
- The text after `@ai` is sent to the LLM, and the reply is posted in the same chat as a reply to the original message (via the user's connected account).
- Conversation history (last 5 exchanges) is included for context — stored in Supabase.
- Rate limiting prevents abuse (5 requests/user/minute in-memory).

## Setup

### 1. Create the bot on Telegram

1. Open [@BotFather](https://t.me/BotFather) on Telegram.
2. Send `/newbot` and follow the prompts. Choose the username `quibo_ai_bot`.
3. Copy the **bot token** — this is your `BOT_TOKEN`.

### 2. No BotFather configuration needed

The webhook is registered automatically on startup. No manual `/setwebhook` in BotFather required.

### 3. Connect the bot via Chat Automation

1. Open Telegram **Settings > Chat Automation**.
2. Tap **Connect Bot** and enter `@quibo_ai_bot`.
3. Configure the keyword trigger: set `@ai` as the trigger keyword.
4. Choose the scope: **All chats** or specific chats.
5. The bot will now receive `business_message` updates whenever `@ai` is typed.

### 4. Supabase table

Run this SQL in the Supabase SQL editor:

```sql
CREATE TABLE quibo_conversations (
    id BIGSERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_quibo_conversations_key ON quibo_conversations (chat_id, user_id);
CREATE INDEX idx_quibo_conversations_created_at ON quibo_conversations (created_at);
```

### 5. Environment variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

| Variable         | Description                      |
|------------------|----------------------------------|
| BOT_TOKEN        | Telegram bot token from BotFather|
| WEBHOOK_SECRET   | Arbitrary secret for webhook auth|
| LLM_BASE_URL     | OpenAI-compatible base URL       |
| LLM_API_KEY      | API key for the LLM provider     |
| LLM_MODEL        | Model name (e.g. gpt-4o-mini)    |
| SUPABASE_URL     | Supabase project URL             |
| SUPABASE_KEY     | Supabase service_role key        |
| PUBLIC_URL       | Your Railway app URL (e.g. `https://quibo-production.up.railway.app`) |

### 6. Run locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

For local testing, use [ngrok](https://ngrok.com) to expose your server and set `PUBLIC_URL` to the ngrok URL.

### 7. Deploy to Railway

Connect your repository to [Railway](https://railway.app) and set the environment variables above. Railway will auto-detect the Dockerfile.

## Usage

In any chat where you've enabled the Chat Automation, type:

```
@ai what is the capital of France?
```

The bot will reply inline in the chat, appearing as sent by you.

## Notes

- The bot only processes messages containing `@ai` (case-insensitive) — all others are ignored.
- Only `business_message` and `message` update types are handled.
- Webhook requests are validated against `WEBHOOK_SECRET` via the `X-Telegram-Bot-Api-Secret-Token` header.
- Response length is capped at 500 characters.
- Old conversation history (>24h) is cleaned up on each request.
