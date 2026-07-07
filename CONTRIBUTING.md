# Contributing

## Setup (zero-infra)
```bash
python -m venv .venv && . .venv/Scripts/activate   # or source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                                # set BOT_TOKEN to run the bot
python -m scripts.init_db                           # SQLite dev DB
```
No Postgres/Redis needed for tests: `DATABASE_URL=sqlite+aiosqlite:///./dev.db`
and `REDIS_URL=memory://` (fakeredis).

## Run it locally
```bash
uvicorn scripts.mock_ai_server:app --port 8088      # keyless AI (optional)
uvicorn api.main:app --reload                        # API + Mini App + admin SPAs
python -m bot.main                                   # the bot (needs BOT_TOKEN)
arq workers.main.WorkerSettings                      # worker (needs real Redis)
```

## Before you push
```bash
ruff check .                       # lint (CI gate)
pytest -q                          # backend tests
python -m scripts.check_migrations # model<->migration drift
(cd miniapp && npm run test && npm run build)
(cd admin   && npm run test && npm run build)
```

## Conventions
- **Style:** ruff (`E,F,I,UP,B`), line length 100. Match surrounding code.
- **Migrations:** every model change needs an Alembic revision; keep them
  idempotent (guards) so they coexist with `create_all` dev DBs. CI fails on drift.
- **i18n:** user-facing strings go through `core.i18n` / Mini App `t()`; all 8
  locales must have every key (guarded by `tests/test_i18n.py`).
- **Money/quota:** deduct via the atomic services (`credits`/`packs`/`quota`),
  refund via `refund_job`. Never hand-roll balance math in a handler.
- **Tests:** add/adjust tests with every change; regression tests for every bug.

## Commits / PRs
- Conventional, atomic commits (`feat:`, `fix:`, `ci:`, `docs:`…).
- PRs must pass CI. Describe the change + how you verified it.
- Update `CHANGELOG.md` for user-visible changes.
- Co-author trailer if pairing with an AI assistant.

## Security
Never commit secrets (`.env`, DBs, `ADMIN_LOGIN.txt` are gitignored). Report
vulnerabilities privately — see [docs/SECURITY.md](docs/SECURITY.md).
