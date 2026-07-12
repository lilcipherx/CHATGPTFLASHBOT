# Loop Engineering — loop-log

Zero-trust engineering loop for CHATGPTFLASHBOT. Every claim below is verified against the
actual tree / actual command output at the stated SHA — not against README / CLAUDE.md /
older audit reports.

Branch: `claude/loop-engineering` (from `main` @ `bb44014ed2c4765c47197dad51df52cc16562c86`).

---

## Loop 0 — Independent discovery + baseline

Date: 2026-07-13. Base SHA: `bb44014` (== `origin/main`).

### Repo shape (verified via `git ls-files`)
- 592 tracked files. Top areas: `tests/` 155, `core/` 111, `admin/` 57, `migrations/` 46,
  `miniapp/` 44, `bot/` 44, `api/` 38, `scripts/` 20, `docs/` 20, `workers/` 16,
  `monitoring/` 8, `.github/` 3.
- Python: core 111, bot 44, api 38, workers 16, scripts 10, migrations 44, tests 155.
- Two Vite/React 18 + TS SPAs: `miniapp/` (Telegram Mini App, has Playwright e2e) and
  `admin/` (Admin Panel, no e2e).

### Flow map (verified from source, not docs)
```
Telegram Bot (aiogram, bot/main.py)
  dispatcher middlewares: Throttling -> DBSession -> UserContext (outer);
                          Ban -> Maintenance -> ChannelGate (per message/callback/pre_checkout/inline)
  router order: start..misc..(kling before video)..(gift before premium)..groups..chat(catch-all last)
  payments: Stars XTR (premium.py pre_checkout single handler approves sub:/pack:/credits:/gift:/avatar),
            successful_payment -> _apply_stars_payment (idempotent on charge id),
            refunds via bot.refund_star_payment, external gateways via core.payments.service.create_checkout
        |
Mini App (miniapp/, X-Init-Data header) --> FastAPI api/routers/miniapp.py (24 routes)
Admin Panel (admin/, httpOnly cookie JWT) --> FastAPI api/admin/* (require_role RBAC, IP allowlist, 2FA)
        |
FastAPI (api/main.py, gunicorn -w4 + uvicorn) ~204 endpoints / 28 files
  webhooks.py: Telegram (constant-time secret, redis update-id dedup) + gateway (sig/IP verify, idempotent on gateway_tx_id)
        |
core/services (billing, checkout, refunds, credits, pricing, packs, promos, quota, ai_routing, ...)
core/payments (yookassa/stripe/crypto/tribute gateways) | core/ai_router (provider adapters + registry)
        |
PostgreSQL (SQLAlchemy 2.0 async, core/db.py: sqlite|pgbouncer|pool modes) ~34 tables
Redis (FSM storage + ARQ queue + dedup) | MinIO/S3 (media) | omniroute (text gateway)
        |
ARQ workers (workers/main.py: WorkerSettings pool + BeatSettings scheduler, 15 DB-gated cron tasks)
```

### Baseline quality gates (actual command output at SHA bb44014)

| Gate | Command | Result |
|------|---------|--------|
| ruff check | `ruff check .` | **PASS** — All checks passed |
| ruff format | `ruff format --check .` | 400 files would reformat — **INFORMATIONAL** in CI (`|| true`), not a gate |
| pytest | `pytest -q` | **PASS** — 905 passed, 0 failed (494s) |
| coverage | `pytest --cov=... --fail-under=67` | **PASS** — TOTAL 68% (14296 stmt, 4560 miss); ratchet 67 |
| mypy | `mypy core api bot workers --ignore-missing-imports` | 306 errors — **NON-BLOCKING** in CI (`|| true`); mostly aiogram `Message|None` union-attr + SQLAlchemy typing FP |
| bandit | `bandit -r core api bot workers -ll -q` | **PASS** — exit 0, no medium/high findings |
| pip-audit | `pip-audit -r requirements.txt` | **BLOCKED locally** — this venv lacks stdlib `venv` module (pip-audit import error). Runs in CI. |
| alembic heads | `alembic heads` | **PASS** — single head `0042_search_model` |
| alembic upgrade | `alembic upgrade head` | **PASS** |
| check_migrations | `python -m scripts.check_migrations` | **PASS** — "OK: migrations reproduce the models (no drift)" |
| miniapp vitest | `npm test` | **PASS** — 17 passed (4 files) |
| miniapp tsc | `npx tsc --noEmit` | **PASS** — exit 0 |
| miniapp build | `npm run build` | **PASS** |
| miniapp e2e | `npx playwright test` | **PASS** — 4 passed |
| admin vitest | `npm test` | **PASS** — 26 passed (6 files) |
| admin tsc | `npx tsc --noEmit` | **PASS** — exit 0 |
| admin build | `npm run build` | **PASS** |
| npm audit (both SPAs) | `npm audit` | 5 vulns each (3 mod/1 high/1 crit) — all `esbuild <=0.24.2` transitive **dev-only** (vite/vitest); prod build unaffected |
| docker build | `docker compose build` | **DEFERRED** — Docker not verified locally yet (ops domain) |

### Baseline verdict
Suite is materially green. No P0 uncovered in Loop 0 discovery. The prior `docs/audit/`
claims (886 passed / 68% cov) are consistent-ish but stale — actual is 905 passed.
`docs/loop/` did not previously exist (created this loop). Live-AWS drift claims from
`docs/audit/aws-production-inventory.md` are treated as UNVERIFIED until re-checked via
`ssh flashbot` (read-only) in the ops/security domain.

### L1 payments — partial verification already done in Loop 0 (money-path core)
Zero-trust re-verification of the money-critical idempotency/atomicity/refund core:
- `core/services/billing.py:_record_tx` — race-safe idempotency: SELECT pre-check + INSERT
  inside `begin_nested()` SAVEPOINT catching `IntegrityError` on `unique(gateway_tx_id)`,
  leaving the outer tx usable. CONFIRMED correct (defends concurrent webhook delivery).
- `core/payments/service.py:apply_event` — amount-tamper guard (±1 minor), quoted-minor vs
  price-table, referral reward retried even on duplicate (idempotent on `referrals.referred_id`).
- `core/services/refunds.py:refund_stars/refund_job` — money-first ordering, `FOR UPDATE`
  row lock, re-check status under lock, conditional `UPDATE ... WHERE refunded_at IS NULL`
  claim (rowcount-0 = already refunded). CONFIRMED race-safe (worker vs stuck-job sweep).
Verdict: no P0/P1 in the payment idempotency/refund core. Claims match tests.

---

## Loop L2 — auth / RBAC / secrets (partial, candidate findings)

Resolved the three concrete auth candidates from Loop 0, all DISMISSED as fail-closed after
reading the actual guard code (not the docs):
- C1 dev-auth bypass — gated on `is_public_deploy` (true on any webhook/PUBLIC_DEPLOY prod);
  fail-closed. Only an explicit operator misconfig (documented) reopens it. No fix.
- C2 admin RBAC — added `tests/test_admin_rbac_coverage.py`: introspects every `/api/admin/*`
  route and asserts `current_admin`/`current_admin_enrolling` in its dependency tree (except
  `/auth/login`, `/auth/refresh`). PASSES → no unguarded admin endpoint. Durable guard.
- C3 JWT default secret — `_require_prod_secret()` runs at import via `settings =
  get_settings()`; public deploy with the placeholder secret hard-fails at boot. No fix.

Commands: `pytest tests/test_admin_rbac_coverage.py -v` → 1 passed (introspected >20 routes).

### Next action
Continue Domain Loop 1: external gateway signature/replay verification (yookassa/stripe/
crypto/tribute webhooks) — the remaining money-critical surface — then L3 generation/quotas.

---
