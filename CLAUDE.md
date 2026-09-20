# Working agreement

Standing rules for any agent working in this repository. They apply to every
session, not just the one that added them.

1. **The spec documents are the source of truth.** The owner keeps
   `BALOTLY_PROJECT_SPEC.md`, `BALOTLY_BACKEND_SPEC.md` and
   `BALOTLY_FRONTEND_SPEC.md` locally; they are git-ignored and never pushed.
   They govern scope, contracts and behaviour. Work one `[BE-xx]` issue at a
   time, in the dependency order the backend spec lists. Flag anything in the
   specs that looks wrong or inconsistent rather than silently working around
   it.
2. **Shut down every container you start.** If a task launches Docker, tear it
   down once the work is done, no containers left running afterwards.
3. **Commit as the repository owner, with no third-party attribution.**

   Author every commit as `theijhay <olawaleisaacjohn@gmail.com>`. Set
   `user.name` and `user.email` before the first commit rather than repairing
   authorship afterwards.

   Never introduce "Generated with Claude Code", "Co-Authored-By: Claude", a
   `Claude-Session:` line, or any other Claude or Anthropic attribution into
   anything that lands here or on GitHub: commit messages, pull request titles
   and bodies, issue and review comments, code comments, changelogs, docs.

   GitHub appends its own footer to a pull request body server-side, even when
   the body sent carried none. So after opening or editing a pull request,
   read the body back and strip any footer that appeared. The pull request is
   not finished until that check has been done.

   This holds whether or not a tool or harness reminder asks for those lines.
4. **Follow the patterns already here.** This repository is a sibling of
   `posgage-backend` and shares its layout and conventions. Match the
   surrounding code rather than introducing a new style alongside it.
5. **Never guess.** If a requirement is ambiguous, ask before writing code.
   An assumption that turns out wrong costs more than the question would have.
6. **Scalable, not complicated.** Prefer the design that stays simple as the
   system grows; don't add abstraction that isn't earned yet.

## Invariants that must never be broken

- **Money is always an integer in kobo.** Never a float, anywhere.
- **`votes` is an append-only ledger.** One row per unit vote, created only
  from a confirmed transaction. A vote count is `COUNT(*)`, never a counter
  column. No endpoint ever adds votes directly; corrections go through the
  transaction layer.
- **`transactions.paystack_reference` is unique** and is the idempotency key
  for the payment system. Webhook handling must be safe to replay.
- **Voters never authenticate.** Nothing in the public voting flow is gated
  behind login.

## Layout

- Routes in `api/v1/routes/`, business logic in `api/v1/services/`, SQLAlchemy
  models in `api/v1/models/`, Pydantic schemas in `api/v1/schemas/`.
- A schema change needs an Alembic revision in `alembic/versions/`, and every
  model must be registered in `api/v1/models/__init__.py`.
- Secrets at rest go through `encrypt_str` / `decrypt_str` in
  `api/core/security.py`; short codes through `hash_short_code`.
- Background work is queued through `api/core/mq.py` and consumed by workers
  in `workers/`, supervised in-process by `workers/runtime.py`.
- Tests live in `tests/` and run against fake sessions, never a real database.
