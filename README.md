# Quibo Telegram Bot

Quibo is a lightweight, mention-only AI assistant for Telegram groups.

- Works in **Guest Mode** — the bot does **not** need to be added to groups.
- Only responds when explicitly @mentioned.
- Replies inline in the same group chat.
- Stores per-user conversation memory in Supabase.
- Deployed on Railway with FastAPI + webhook.

## Features

- Guest Mode mention handling (works even if bot is not in the group)
- Prompt extraction after `@quibo_ai_bot`
- OpenAI-compatible LLM backend (configurable)
- Per-user rate limiting (in-memory)
- Conversation memory (last messages + 24h expiry)
- Concise responses (< 500 chars)
- Structured logging

## Project Structure

```
.
├── main.py
├── requirements.txt
├── Dockerfile
├── .env.example
└── README.md
```

## Setup

### 1. Create the Telegram Bot

1. Open Telegram and talk to [@BotFather](https://t.me/BotFather)
2. Send `/newbot`
3. Choose a name: **Quibo**
4. Choose a username: `quibo_ai_bot`
5. **Important for Guest Mode**: After creation, send `/setprivacy` → choose your bot → select **Disable**.

   This is required so the bot can see mentions in groups it's not a member of.

### 2. Create Supabase Table

Go to your Supabase project → **SQL Editor** and run:

```sql
create table if not exists quibo_conversations (
  id bigserial primary key,
  chat_id bigint not null,
  user_id bigint not null,
  role text not null check (role in ('user', 'assistant')),
  content text not null,
  created_at timestamptz not null default now()
);

-- Optional but recommended indexes
create index if not exists idx_quibo_chat_user on quibo_conversations(chat_id, user_id);
create index if not exists idx_quibo_created_at on quibo_conversations(created_at);

-- Optional: RLS (recommended for production)
-- alter table quibo_conversations enable row level security;
```

### 3. Environment Variables

Copy the example:

```bash
cp .env.example .env
```

Fill in `.env`:

```env
BOT_TOKEN=123456:ABCDEF...your-telegram-token
WEBHOOK_SECRET=some-long-random-secret-string

LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini

SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### 4. Local Development

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

uvicorn main:app --reload
```

### 5. Set Webhook (for local testing)

You can use ngrok or Railway's automatic deployment.

For manual testing:

```bash
curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -d "url=https://your-domain.com/webhook" \
  -d "secret_token=your-webhook-secret"
```

### 6. Railway Deployment

1. Push this repo to GitHub
2. Go to [Railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Add all variables from `.env` as **Variables**
4. Railway will automatically detect the Dockerfile and deploy
5. After deployment, copy the public Railway URL

6. Set the webhook:

```bash
curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -d "url=https://your-railway-url.up.railway.app/webhook" \
  -d "secret_token=${WEBHOOK_SECRET}"
```

You can also set the webhook from code on startup if preferred.

### 7. Usage in Telegram

In any group (even if the bot is not a member):

```
@quibo_ai_bot what is the capital of France?
```

Quibo will reply directly in the group as a reply to your message.

If you just mention it without a question:

```
@quibo_ai_bot
```

It will send a usage hint.

## Environment Variables Reference

| Variable              | Required | Description                              |
|-----------------------|----------|------------------------------------------|
| BOT_TOKEN             | Yes      | Telegram bot token from BotFather        |
| WEBHOOK_SECRET        | Yes      | Secret for verifying Telegram webhooks   |
| LLM_BASE_URL          | Yes      | OpenAI-compatible endpoint               |
| LLM_API_KEY           | Yes      | API key for the LLM                      |
| LLM_MODEL             | No       | Model name (default: gpt-4o-mini)        |
| SUPABASE_URL          | Yes      | Supabase project URL                     |
| SUPABASE_KEY          | Yes      | Supabase anon/service role key           |
| RATE_LIMIT_PER_MINUTE | No       | Default: 5                               |

## Notes & Limitations

- Memory is per `(chat_id, user_id)` — different people in the same group have separate histories.
- History older than 24 hours is cleaned on each request.
- Rate limiting is in-memory (resets on restart). For heavy use, consider adding Redis.
- Responses are capped at ~500 characters for group chat readability.
- The bot ignores all messages except direct mentions in groups.

## License

MIT — feel free to fork and customize.