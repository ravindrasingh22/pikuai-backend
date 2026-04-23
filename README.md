# PikuAI Backend

Python FastAPI backend for the MVP feature spec in `pikuai-docs/piku_ai_backend_feature_spec_mvp.md`.

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 4000
```

Default API URL:

```text
http://localhost:4000/api/v1
```

## Docker

Run the backend API and Postgres together:

```bash
docker compose up --build
```

Services:

- API: `http://localhost:4000`
- Database: `localhost:5432`
- DB health check: `GET http://localhost:4000/health/db`

The Postgres schema is initialized from:

```text
docker/postgres/init.sql
```

Local environment defaults are documented in `.env.example`.

## Local LLM Configuration

The backend can call a local LLM during `POST /api/v1/chat/message`.

Default provider:

```text
LLM_PROVIDER=ollama
LLM_ENABLED=true
LLM_BASE_URL=http://localhost:11434
LLM_MODEL=mistral:latest
LLM_TIMEOUT_SECONDS=30
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=280
```

When running inside Docker on macOS, compose uses:

```text
LLM_BASE_URL=http://host.docker.internal:11434
```

Start Ollama locally:

```bash
ollama pull mistral:latest
ollama serve
```

Verify backend LLM config:

```bash
curl http://localhost:4000/api/v1/llm/config
```

Use an OpenAI-compatible local server instead:

```text
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=http://localhost:1234/v1
LLM_MODEL=local-model-name
```

Safety behavior:

- `allowed` and `allowed_with_adaptation` prompts call the configured LLM.
- `block_and_redirect` and `escalate` prompts use deterministic safety responses and do not call the LLM.
- If the LLM is unavailable, the API returns a safe fallback answer and marks `llm_used_fallback=true`.

## Implemented API Groups

- `POST /api/v1/admin/auth/login`
- `GET /api/v1/admin/users`
- `POST /api/v1/auth/register-parent`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/2fa/send-code`
- `POST /api/v1/auth/2fa/verify`
- `GET /api/v1/parent/profile`
- `PATCH /api/v1/parent/profile`
- `GET /api/v1/parent/security-settings`
- `GET /api/v1/children`
- `POST /api/v1/children`
- `GET /api/v1/children/:childId`
- `PATCH /api/v1/children/:childId`
- `POST /api/v1/children/:childId/archive`
- `POST /api/v1/children/:childId/age-template/recalculate`
- `GET /api/v1/controls`
- `PATCH /api/v1/controls`
- `GET /api/v1/privacy/settings`
- `PATCH /api/v1/privacy/settings`
- `GET /api/v1/privacy/consents`
- `POST /api/v1/privacy/consents`
- `POST /api/v1/privacy/delete-request`
- `GET /api/v1/billing/plans`
- `POST /api/v1/billing/checkout-session`
- `GET /api/v1/billing/subscription`
- `POST /api/v1/billing/subscription/cancel`
- `POST /api/v1/chat/message`
- `GET /api/v1/chat/threads`
- `GET /api/v1/chat/threads/:threadId`
- `GET /api/v1/dashboard/overview`
- `GET /api/v1/transcripts`
- `GET /api/v1/transcripts/threads/:threadId`
- `GET /api/v1/alerts`
- `GET /api/v1/alerts/:alertId`
- `POST /api/v1/alerts/:alertId/review`
- `POST /api/v1/alerts/:alertId/resolve`
- `GET /api/v1/explainability/messages/:messageId`
- `GET /api/v1/llm/config`
- `GET /api/v1/trust/benchmark-summary`

## Notes

This uses an in-memory store so feature behavior is visible immediately. Replace `app/data/store.py` with database repositories when persistence is introduced.

## Seed Credentials

Database-seeded admin user:

- `admin@pikuai.local` / `admin12345`

Parent/mobile demo user:

- `ravin@example.com`

Parent/mobile accounts are intentionally rejected by `POST /api/v1/admin/auth/login`.
