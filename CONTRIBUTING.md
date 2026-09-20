# Contributing

How work lands in this repository. Read this before picking up an issue.

## Issues and branches

Every piece of work is a GitHub issue named `[BE-xx] Title`. Take the issue
you are assigned, branch from `main` as `feature/be-xx-short-name`, and open
a pull request back to `main` when it is done. One issue per pull request.
Link the issue in the PR body.

Do not start an issue whose "Depends on" issues are not merged yet.

## Layout

* `api/v1/routes/` holds the FastAPI routers. A route parses input, calls a
  service, and shapes the response. No business logic in a route.
* `api/v1/services/` holds the business logic. Services take an
  `AsyncSession` and plain values, never a `Request`.
* `api/v1/models/` holds the SQLAlchemy models. Register every new model in
  `api/v1/models/__init__.py`.
* `api/v1/schemas/` holds the Pydantic request and response models.
* `alembic/versions/` holds migrations. Every schema change needs one. Never
  edit or delete a migration that has been merged; add a new one.
* `workers/` holds background consumers. Register each in
  `workers/runtime.py` so the API process supervises it.
* `tests/` holds pytest suites. Tests use fake sessions and never connect to
  a real database.

## Response shape

Successful responses go through `api.utils.success_response.success_response`:

```json
{ "status_code": 200, "success": true, "message": "Contest created.", "data": { } }
```

Errors go through `api.core.errors.api_error` and always look like this:

```json
{ "detail": { "code": "CONTEST_NOT_FOUND", "message": "That contest does not exist." } }
```

The `code` is a stable SNAKE_CASE string the frontend branches on. Every
issue lists the codes its endpoints return. Use those exact strings.

Validation failures from Pydantic return FastAPI's default 422 body; the
frontend treats any 422 as "fix your input".

## Rules that are never broken

* Money is an integer in kobo. Never a float, never naira, anywhere in the
  backend.
* `votes` is append only. One row per unit vote, written only by the webhook
  handler from a confirmed transaction. Vote counts are `COUNT(*)`. No
  endpoint ever inserts, updates or deletes a vote directly.
* `transactions.paystack_reference` is unique and every webhook must be safe
  to receive twice.
* Voters never log in. Nothing under `/vote/` requires a token.
* Organizer endpoints filter by the caller's `organization_id` in the query.
  A row from another organization returns 404, not 403, so the response does
  not confirm it exists.
* Secrets at rest go through `encrypt_str` / `decrypt_str` in
  `api/core/security.py`. Never log a secret, a token or an account number.
* Any new configuration value goes in `api/utils/settings.py` with a comment
  and in `.env.example` with a comment saying what it is for.

## Before you open a pull request

```bash
DEBUG=false .venv/bin/pytest -q
DEBUG=false .venv/bin/alembic upgrade head      # against the compose Postgres
DEBUG=false .venv/bin/alembic check             # models and migration agree
```

CI runs the same checks plus a start up smoke test. A red CI is not ready
for review.

## Pull request body

Say what changed and why, in terms of behaviour. List the acceptance
criteria from the issue and tick the ones you verified, and say how. If you
made a call the issue did not cover, say so in the PR so it can be reviewed.
