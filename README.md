# balotly-backend

Balotly is a self-serve platform for paid campus and school voting: contests,
awards, and SUG-style elections. It replaces the usual WhatsApp
poster-plus-bank-transfer setup with a shareable link, instant checkout, and a
live, tamper-resistant vote count. Every vote is tied to a verified payment via
webhook, so organizers get a real-time tally instead of trusting candidates to
self-report screenshots.

FastAPI service using async SQLAlchemy with PostgreSQL, Redis for caching and
rate limiting, and RabbitMQ for background work (webhook processing, poster
rendering, settlement, notifications) supervised inside the API process.

Work is tracked as GitHub issues (BE-01 to BE-16), one per slice, in the
dependency order they list.

## Local development

```bash
cp .env.example .env   # then set SECRET_KEY and ENCRYPTION_KEY (see comments)
docker compose up --build
```

The API runs at `http://localhost:8001` (host ports are offset by 2 so this
stack coexists with Posgage's). Its container applies Alembic migrations before
starting Uvicorn. In the current all-in-one mode, that same FastAPI process
supervises the background workers, so the command above starts the complete
application. A worker exception is logged and only that worker is restarted
with bounded backoff; API liveness and the sibling workers remain available.

Keep `RUN_EMBEDDED_WORKERS=true`, one Uvicorn process, and one API container
replica in this mode. Do not add Uvicorn `--workers`. `GET /health` reports
worker state without making a retrying worker fail the API liveness check.

For a local virtual environment:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
DEBUG=false .venv/bin/alembic upgrade head
DEBUG=false .venv/bin/pytest -q
DEBUG=true .venv/bin/uvicorn main:app --reload
```

Never delete or regenerate a migration that has been applied anywhere. Add a
new revision instead.

## Schema

Ten tables, all created by the initial revision. The two that carry the
product's integrity guarantees:

- `transactions.paystack_reference` is unique. It is the idempotency key for
  the whole payment system; a redelivered webhook finds its row and stops.
- `votes` is append-only: one row per unit vote, no count column, no
  `updated_at`, and database triggers that refuse `UPDATE`, `DELETE` and
  `TRUNCATE`.
  A vote count is always `COUNT(*)`, so it is always reconstructable from
  confirmed transactions.

One vote per matric number is a partial unique index on `transactions`,
active only for rows whose contest caps votes per identity.
