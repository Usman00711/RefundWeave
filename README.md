# Sole Syntax AI Customer Support Agent

An AI-powered customer support agent for **Sole Syntax**, a shoe e-commerce brand. The agent understands natural-language refund requests, then moves them through an explicit, policy-controlled workflow with verified ownership and a customer confirmation gate.

## Features

- **Conversational refund handling** — customers describe their issue in plain language
- **Policy enforcement** — agent strictly applies Sole Syntax's refund policy (return windows, worn items, final sale, defects, loyalty tiers)
- **Explicit workflow** — identify customer → verify ownership → evaluate policy → confirm → execute
- **Persistent session context** — LangGraph checkpoints retain the verified customer and order across follow-up messages
- **Confirmation gate** — refund writes require a separate, explicit customer confirmation
- **Deterministic guardrails** — ownership and eligibility are revalidated inside every refund transaction
- **Visible workflow steps** — completed safety stages are shown as collapsible steps in the chat UI
- **Voice interface** — speak requests via browser microphone; agent responses read aloud (Web Speech API, no API key required)
- **Terminal reasoning logs** — colorized, structured agent trace printed to terminal during every session

## Tech Stack

| Layer | Technology |
|---|---|
| Agent framework | [LangGraph](https://github.com/langchain-ai/langgraph) (explicit state machine + checkpoints) |
| LLM | [OpenRouter](https://openrouter.ai) — `openai/gpt-oss-120b:free` |
| API | [FastAPI](https://fastapi.tiangolo.com/) with typed OpenAPI contracts |
| Chat UI | [Chainlit](https://chainlit.io) |
| Database | MySQL 8.4, SQLAlchemy 2, Alembic migrations |
| Runtime | Docker Compose with health-ordered startup |
| Voice | Browser Web Speech API (STT + TTS, zero cost) |
| Terminal logs | [Rich](https://github.com/Textualize/rich) |
| Python env | [uv](https://github.com/astral-sh/uv) |

## Project Structure

```
ai-cs-agent-langgraph/
├── app.py                  # Chainlit entry point
├── api/                    # Versioned FastAPI routes and schemas
├── application/            # Typed services shared by API and agent tools
├── infrastructure/         # SQLAlchemy models, sessions, and repositories
├── migrations/             # Alembic schema migrations
├── agent/
│   ├── graph.py            # Deterministic LangGraph workflow and safety gates
│   ├── interpreter.py      # Narrow LLM boundary for intent and identifier extraction
│   ├── prompts.py          # Extraction-only prompt; no business authorization
│   ├── state.py            # Typed customer, order, policy, and workflow state
│   └── tracer.py           # Rich terminal reasoning logger
├── domain/
│   └── refunds.py          # Typed, deterministic refund policy decisions
├── tools/
│   ├── crm_tools.py        # lookup_customer, get_order_details
│   ├── policy_tools.py     # check_refund_eligibility
│   └── refund_tools.py     # process_refund, deny_refund, escalate_to_human
├── data/
│   ├── seed_db.py          # Repeatable MySQL demo-data seeder
│   └── refund_policy.md    # Sole Syntax refund policy document
├── public/
    └── voice.js            # Web Speech API integration
├── Dockerfile              # Shared API/Chainlit image
└── compose.yaml            # MySQL, migrations, seed, API, and UI
```

## Getting Started

### Prerequisites

- Docker Desktop with Docker Compose
- An [OpenRouter](https://openrouter.ai) API key for AI chat requests
- Python 3.13+ and [uv](https://docs.astral.sh/uv/) only when running tests locally

### Docker Quick Start

```bash
cp .env.example .env
```

Set `OPENROUTER_API_KEY` in `.env`, then start the complete stack:

```bash
docker compose up --build -d
docker compose ps
```

Compose waits for MySQL to become healthy, runs the Alembic migration, seeds the
database once, and then starts both interfaces:

- Chainlit UI: [http://localhost:8000](http://localhost:8000)
- FastAPI: [http://localhost:8001](http://localhost:8001)
- OpenAPI docs: [http://localhost:8001/api/docs](http://localhost:8001/api/docs)

Inspect startup output with:

```bash
docker compose logs -f api chainlit
```

The API and database can run without an OpenRouter key. The key is required when a
Chainlit message invokes the language model.

### Validate the Running Stack

Check API and database readiness:

```bash
curl http://localhost:8001/api/v1/health
```

Expected result:

```json
{"status":"ok","database":"ready","version":"v1"}
```

Check a seeded policy scenario:

```bash
curl -X POST http://localhost:8001/api/v1/refunds/eligibility \
  -H 'Content-Type: application/json' \
  -d '{"customer_query":"Alice Johnson","order_id":"ORD-001"}'
```

Inspect MySQL records directly:

```bash
docker compose exec mysql mysql -usole_syntax -psole_syntax sole_syntax \
  -e "SELECT order_id, product, refund_status FROM orders LIMIT 5;"
```

Restore all 15 demo scenarios after testing refunds or denials:

```bash
docker compose --profile tools run --rm seed-reset
```

Stop containers while preserving MySQL data:

```bash
docker compose down
```

Use `docker compose down -v` only when you intentionally want to delete the MySQL
volume and recreate the database from scratch.

### Local Development Against Docker MySQL

Start only MySQL, apply migrations, seed, and run each Python interface locally:

```bash
docker compose up -d mysql
uv sync
uv run alembic upgrade head
uv run python -m data.seed_db
uv run python -m uvicorn api.main:app --reload --port 8001
```

In another terminal:

```bash
uv run python -m chainlit run app.py
```

The default host database URL is configured in `.env.example`. Alembic is the only
schema creation mechanism; the seed command never creates tables.

The database variable is named `SOLE_SYNTAX_DATABASE_URL` intentionally. Do not rename
it to `DATABASE_URL`, because Chainlit reserves that name for its PostgreSQL data layer.

### API v1

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/v1/health` | Database readiness |
| `POST` | `/api/v1/customers/lookup` | Exact customer lookup |
| `POST` | `/api/v1/orders/lookup` | Ownership-aware order lookup |
| `POST` | `/api/v1/refunds/eligibility` | Structured policy decision |
| `POST` | `/api/v1/refunds/{order_id}/confirm` | Confirmed, revalidated refund |

## Usage

Start a conversation by providing your name and order ID. Example:

> "Hi, I'm Alice Johnson. I'd like to return my order ORD-001."

The agent will look up your account, verify order ownership, and check the refund policy. If the order is eligible, it pauses without changing the database and asks you to reply `confirm refund`. A denial is explained without automatically mutating the order, and you may request a human escalation.

For voice input, click the **🎤 floating button** (bottom-right). Your spoken request is transcribed and submitted automatically. The agent's response is also read aloud.

## How It Works

1. The user message arrives through Chainlit with a unique LangGraph thread ID
2. The LLM extracts only customer/order identifiers and intent; it cannot authorize actions
3. Deterministic nodes identify the customer and verify that the order belongs to them
4. The domain service evaluates policy from trusted database facts
5. Eligible requests stop at an explicit confirmation gate
6. A confirmed refund rechecks policy inside a locked MySQL transaction before writing
7. Session checkpoints retain verified context for follow-ups, and the UI shows each completed stage

## Quality Checks

The policy suite runs without contacting an LLM and covers loyalty return-window
boundaries, defects, final-sale products, worn products, proof of purchase, custom
products, ownership mismatches, direct guardrail bypasses, duplicate operations,
concurrent refund attempts, required workflow ordering, confirmation, session isolation,
follow-up context, cancellation, escalation, and prompt-injection attempts.

```bash
uv run pytest -m "not mysql"
uv run ruff check .
```

Run the real MySQL migration and concurrency tests using the disposable test
container on port 3307:

```bash
docker compose --profile test up -d --wait mysql-test
TEST_DATABASE_URL='mysql+pymysql://sole_syntax:sole_syntax@127.0.0.1:3307/sole_syntax_test?charset=utf8mb4' \
  uv run pytest -m mysql
docker compose --profile test stop mysql-test
```

Check that the live schema still matches the SQLAlchemy models:

```bash
uv run alembic check
```

## Current Limitations

- This is a demonstration system: refunds and escalations do not interact with real
  payment or ticketing services.
- MySQL contains fictional demo customers and simulated financial actions only.
- Conversation checkpoints are held in application memory for this phase. They survive
  messages in the same running chat session, but are cleared when Chainlit restarts.
- Do not use this portfolio demo with real customer or payment data.
