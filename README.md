# Quibo — Telegram Bot

A FastAPI-based Telegram bot that responds when @mentioned in group chats using Telegram's Guest Mode feature. Backed by an OpenAI-compatible LLM and Supabase for conversation memory.

## How it works

- The bot receives updates via a **webhook** (POST /webhook).
- It only processes group messages where `@quibo_ai_bot` is mentioned.
- The text after the mention is sent to the LLM, and the reply is posted in the same chat as a reply to the original message.
- Conversation history (last 5 exchanges) is included for context — stored in Supabase.
- Rate limiting prevents spam (5 requests/user/minute in-memory).

## Setup

### 1. Create the bot on Telegram

1. Open [@BotFather](https://t.me/BotFather) on Telegram.
2. Send `/newbot` and follow the prompts. Choose the username `quibo_ai_bot`.
3. Copy the **bot token** — this is your `BOT_TOKEN`.

### 2. Enable Guest Mode (no group membership required)

In BotFather, send:
```
/mybots → select quibo_ai_bot → Bot Settings → Group Privacy → Turn off
```

**Wait — do the opposite:** To allow the bot to read all messages in groups it's a member of, you'd disable Group Privacy. But since we want **Guest Mode** (read only the specific mention message without being added to the group), you need to **leave Group Privacy ON**. The bot will receive updates only when @mentioned via Telegram's inline mention feature.

Then set the webhook URL:
```
/setwebhook
```
Enter: `https://your-railway-app.railway.app/webhook`

### 3. Supabase table

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

### 4. Environment variables

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

### 5. Run locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

For local testing, use a tool like [ngrok](https://ngrok.com) to expose your local server and set the webhook URL in BotFather.

### 6. Deploy to Railway

Connect your repository to [Railway](https://railway.app) and set the environment variables above. Railway will auto-detect the Dockerfile.

## Usage

In any Telegram group, type:
```
@quibo_ai_bot what is the capital of France?
```

The bot will reply inline in the group thread.

## Notes

- The bot ignores private DMs and non-mention messages.
- Webhook requests are validated against `WEBHOOK_SECRET` (sent as `X-Telegram-Bot-Api-Secret-Token` header).
- Response length is capped at 500 characters.
- Old conversation history (>24h) is cleaned up on each request.
