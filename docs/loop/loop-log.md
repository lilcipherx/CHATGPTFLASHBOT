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

### L1 gateway webhook signature verification — verified clean
- `crypto_gw.verify_webhook`: HMAC-SHA256 over body with sha256(token) key, constant-time
  compare, raise `PaymentError` on mismatch (→ 200 ack, no apply). Fail-closed.
- `tribute_gw.verify_webhook`: HMAC-SHA256 + constant-time compare; ALSO inert (returns None)
  until `TRIBUTE_API_VERIFIED=true` — refuses to credit on an unverified mapping. Fail-safe.
- `yookassa` (unsigned): source-IP allowlist, fail-closed on public deploy when unset
  (`webhooks.py:105-125`), XFF right-most hop behind Caddy.
- `stripe`: SDK `construct_event` + boot guard requiring `STRIPE_WEBHOOK_SECRET` when
  `STRIPE_SECRET` set (`config.py:303`).
Verdict: no forgeable webhook path. L1 payments domain closed — no P0/P1.

---

## Loop L3 — generation / quotas / idempotency (partial)

Verified the money-adjacent generation charge path (`api/routers/miniapp.py:effect_generate`
/ `video_generate`), the highest-risk L3 surface:
- Per-submit idempotency: Redis SETNX `first_seen` on a client `idempotency_key` (fail-open),
  duplicate double-tap → 409, no second job/charge; key released on any pre-commit failure.
- Atomic charge: `try_consume*/try_consume(commit=False)` holds the balance row lock, job row
  added in the SAME transaction, single `session.commit()` lands charge+job atomically; any
  pre-commit failure rolls back the charge (balance untouched).
- Post-commit `_enqueue_or_refund`: enqueue failure → `refund_job` (race-safe, verified in L1);
  a crash between commit and enqueue is recovered by the `sweep_stuck_jobs` cron.
- Balance charge under `session.refresh(user, with_for_update=True)` (`quota.consume_text:169`).
Verdict: charge atomicity + idempotency CONFIRMED correct. No P0/P1.

---

## Loop L4 — database / migrations / indexes / pools

### F1 verified (ops): GitHub Actions CI non-functional — see findings.md. PR #3 opened;
in-repo merge blocked by the harness (no human review + no functioning CI) — correct guardrail.

### F2 FIXED (P2 database): missing `ix_users_bot_id` on the migrated schema
Confirmed real drift the `check_migrations` gate hides (index-only diffs filtered as
SQLite-benign; `create_all` fixtures mask it). TDD: `tests/test_migration_bot_id_index.py`
(subprocess alembic upgrade + inspect) went RED at 0042, GREEN after adding
`migrations/versions/0043_users_bot_id_index.py` (CONCURRENTLY + autocommit_block, idempotent,
reversible). Single head now `0043`; check_migrations OK; 22-test cross-domain subset green.
This is the branch's FIRST production-relevant change — a deploy would now run 0043 (safe,
concurrent index backfill).

### F3 FIXED (P2 database): 3 more un-migrated model indexes (generalised from F2)
Diagnostic (Base.metadata vs migrated schema) surfaced `gifts.buyer_id`, `gifts.redeemed_by`,
`contest_entries.user_id` — all `index=True`, none migrated. Fixed in
`migrations/versions/0044_missing_model_indexes.py`. The regression test was GENERALISED to
assert every model-declared index exists on the migrated schema — a durable guard for the whole
bug class. Head now `0044`; reversible; check_migrations OK; 30-test gifts/contests regression green.

### DB layer reviewed (no further P0/P1)
- `core/db.py`: three engine modes (sqlite NullPool / pgbouncer NullPool + statement_cache=0 /
  standard pool pre_ping size10+overflow5) — correct for transaction-pooled PgBouncer.
- `_record_tx`, `refund_job`, `quota.consume_text` use `with_for_update` (Postgres row locks;
  no-op on SQLite, which the config guard forbids in prod). Consistent.
- Migration chain 0000→0043 linear, single head, no multi-head risk; backfill index migrations
  all use the CONCURRENTLY+autocommit_block safe pattern.

---

## Loop L3 remainder + L5 (workers / uploads / storage) — verified clean

### L3 workers idempotency — CONFIRMED safe
- `workers/photoeffect_tasks.process_photoeffect_job`: claims via conditional `UPDATE ... WHERE
  status='pending' AND refunded_at IS NULL` → rowcount 0 returns (no double-process); on failure
  re-checks `status=='processing'` before `refund_job` (no double-refund vs the stuck-job sweep).
  `refund_job` itself is race-safe (L1). Same claim/refund pattern across the generation workers.

### L5 uploads / storage / SSRF — CONFIRMED safe
- `storage.save_upload`: keys are `uuid4().hex` (no user-controlled filename → no path traversal);
  content-type mapped, default `application/octet-stream`. Delete guards against `/media/..`.
- `storage.rehost_remote`: real SSRF defense — `_is_ssrf_url_async` resolves DNS via getaddrinfo
  and rejects if ANY resolved IP `is_loopback/is_link_local/is_private/is_reserved` (blocks
  169.254.169.254 metadata, 10/192.168/172.16, localhost). Manual per-hop redirect re-validation
  (follow_redirects=False) closes the redirect-to-metadata + DNS-rebinding gap; streaming body
  with Content-Length pre-check + running-total cap prevents OOM. No P0/P1.

### Migrations 0043/0044 production re-verification (per user request)
See `docs/loop/migration-runbook.md`. Verified: linear single head `0044`; env.py runs all
migrations in ONE outer transaction, and `autocommit_block()` correctly hosts `CREATE INDEX
CONCURRENTLY` outside it — identical to the already-deployed 0004/0007/0021/0023/0038 pattern.
Additive indexes only; idempotent + reversible (`DROP INDEX CONCURRENTLY` downgrade). Runbook
documents backup, INVALID-index recovery, and an app-only rollback (old app runs fine against
the indexed schema — no schema downgrade needed).

### Next action
L7 infra: (1) F1 CI remediation — precise root cause + a non-bypassing local CI-mirror gate +
owner runbook; (2) read-only AWS inventory via `ssh flashbot` (deployed SHA, container health,
ports/SG, `alembic current`, backup). Then L6 Playwright e2e (Mini App/Admin). Merge/deploy
held for a single final gate after convergence (per user).

---
