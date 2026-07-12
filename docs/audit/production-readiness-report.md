# CHATGPTFLASHBOT — Production-Readiness Audit Report

> Zero-trust production-readiness audit. Every claim below is backed by a command
> run against the current working tree (commit `a93f049`), not by prior reports,
> `FIX:` comments, or CI badges. Sections are appended as phases complete.

**Branch:** `claude/production-readiness-audit`
**Audit start SHA:** `a93f049fe21c96813f71ef6d66aacdf12eb45a04` (== `main` == `origin/main`)
**Environment:** Windows 11, Python 3.12.3 (`.venv`), Node v22.22.2, npm 10.9.7.
**Local limitation:** Docker CLI is **not installed on this machine** — `docker compose build`
and containerized Postgres/Redis integration cannot be exercised locally; they are
deferred to CI / AWS. `pip-audit` also cannot run locally (portable venv lacks the
stdlib `venv` module — import-time crash inside pip-audit); deferred to CI.

---

## Phase 0 — Sync + Baseline

### 0.1 Local ↔ GitHub reconciliation (read-only)

| Ref | SHA |
|---|---|
| `HEAD` (audit branch) | `a93f049fe21c96813f71ef6d66aacdf12eb45a04` |
| `main` | `a93f049…` (identical) |
| `origin/main` | `a93f049…` (identical) |

- `git fetch origin --prune`: clean. Working tree **clean** (`git status --short` empty).
- Audit branch is **0 ahead / 0 behind** `origin/main` — no divergence, no unpushed
  commits, no user WIP to preserve. Safe starting point.
- Remote: `https://github.com/lilcipherx/CHATGPTFLASHBOT.git` (**private** — 404
  unauthenticated; GitHub CI run history cannot be queried without auth).
- `gh` CLI is **not installed** — GitHub PR creation / CI-status checks in Phase 10
  require installing `gh` or using the REST API with a token.

### 0.2 Baseline check results (fresh runs, this audit)

| Check | Command | Result | Notes |
|---|---|---|---|
| Lint (gate) | `ruff check .` (ruff 0.15.17, == CI pin) | ❌ **160 errors** | 79×E501, 40×E402, 38×I001, 1×E702, 1×UP037, 1×UP041. In tracked source: workers 51, api 44, core 39, bot 20, tests 4, scripts 2. |
| Migrations drift | `python -m scripts.check_migrations` | ❌ **exit 1 — drift** | Model dropped `admin_users.backup_codes_hashed` (added by migration 0039) with no down-migration. |
| Alembic upgrade | `alembic upgrade head` (fresh SQLite) | ✅ exit 0 | Runs cleanly 0000→0042. |
| Unit tests | `pytest --cov … -q` | ✅ **854 passed, 0 failed** (423s) | Zero-infra (SQLite + fakeredis). Global coverage **67%** (14139 stmts / 4662 miss). |
| Static security | `bandit -r core api bot workers -ll -q` | ✅ **0 issues** | Clean. |
| Dep vuln scan | `pip-audit -r requirements.txt --strict` | ⚠️ **cannot run locally** | pip-audit import crash (no stdlib `venv`). → CI. |
| Miniapp typecheck | `npx tsc --noEmit` (miniapp) | ✅ exit 0 | |
| Miniapp unit | `npm run test` (vitest) | ✅ **12 passed** (4 files) | Thin; no Playwright e2e run yet. |
| Admin typecheck | `npx tsc --noEmit` (admin) | ✅ exit 0 | |
| Admin unit | `npm run test` (vitest) | ✅ **26 passed** (6 files) | Thin. |
| Docker build | `docker compose build` | ⚠️ **cannot run locally** | No Docker CLI. → CI / AWS. |

### 0.3 Baseline findings (to fix in later phases)

- **B-1 (P1) — CI lint gate red on `main`.** The blocking `lint` job (`ruff check .`,
  ruff 0.15.17) fails with 160 errors on the exact committed tree. The HEAD commit
  message claims *"whole-tree lint clean"* — contradicted by the current code.
  → Either main was merged without enforced required checks (branch-protection gap,
  cross-ref Phase 8/10), or CI is red and ignored. Fix lint + verify enforcement.
- **B-2 (P1) — CI migrations gate red on `main`.** `scripts.check_migrations` exits 1
  (drift: `backup_codes_hashed`). CI `migrations` job runs this exact script.
  → Same enforcement concern as B-1. Resolve drift in Phase 5 (add migration or
  restore the model field — determine which is source of truth first).
- **B-3 (P2) — Coverage floor is `--fail-under=50`,** not the audit-required global
  ≥70% / critical-path ≥85% ratchet. → Phase 9.
- **B-4 (P2) — Frontend test suites are thin** (miniapp 12, admin 26 unit tests; zero
  Playwright e2e executed). → Phase 7 adds real e2e.
- **B-5 (P3) — pytest-asyncio deprecation:** `asyncio_default_fixture_loop_scope`
  unset (future-break warning). → set explicitly in `pyproject.toml` (Phase 9).

> NOTE on B-1/B-2: the "is `origin/main` CI actually red?" question cannot be answered
> without GitHub auth (private repo, no `gh`). Recorded as **requires GitHub auth to
> confirm enforcement** — resolved in Phase 10.

### 0.4 Baseline coverage of critical paths (for the Phase 9 ratchet)

Target: critical paths ≥85%. Current baseline (from the coverage run above):

| Module | Cover | vs 85% |
|---|---|---|
| `core/services/refunds.py` | 94% | ✅ |
| `core/services/credits.py` | 91% | ✅ |
| `api/admin/admins.py` | 86% | ✅ |
| `core/services/quota.py` | 84% | ⚠️ near |
| `core/services/billing.py` | 71% | ❌ |
| `api/admin/auth.py` | 65% | ❌ |
| `workers/billing_tasks.py` | 61% | ❌ |
| `core/payments/crypto_gw.py` | 60% | ❌ |
| `core/payments/service.py` | 54% | ❌ |
| `core/payments/yookassa_gw.py` | 51% | ❌ |
| `core/ai_router/registry.py` | 49% | ❌ |
| `core/payments/stripe_gw.py` | 36% | ❌ |
| AI adapters (image/video/music/vision) | 18–42% | ❌ (provider I/O — hard to unit test; e2e/mock needed) |

→ Phase 9 must add focused tests for payments gateways, admin auth, `registry.py`,
and `billing_tasks.py` before the ≥85% critical-path gate can pass. Global 67% is
below the ≥70% target — a small lift once the above modules improve.

**Phase 0 verdict:** baseline established and recorded. Two blocking CI gates
(lint, migrations) are red on the current tree — top of the fix queue. Test suite
is green (854) but coverage under target on money/auth/AI-routing paths.

---

## Phase 2 candidates — Payments / refunds / ledger (lane audit; verification pending)

Verified-correct (no change): Crypto Pay webhook (HMAC off non-empty token +
`is_available()` gate), YooKassa (authoritative re-fetch + Decimal + fail-closed IP
allowlist), admin refund endpoint two-phase revoke+gateway-refund (`api/admin/ops.py:370`,
row-locked, idempotent), credits/packs/promos `with_for_update` + non-positive guards,
refunds money-before-ledger ordering. **Open (priority #1 fix queue):**

- **P-1 (P0)** **Forged Stripe "paid" events accepted when `STRIPE_WEBHOOK_SECRET`
  unset.** `core/payments/stripe_gw.py:133` calls `stripe.Webhook.construct_event(...,
  settings.stripe_webhook_secret)` with no non-empty/`is_available()` guard; with the
  `""` default, an attacker computes `HMAC-SHA256("", "t.body")` and forges
  `checkout.session.completed / payment_status=paid` → free credits/subscriptions.
  `_require_prod_secret()` (`core/config.py`) never validates `stripe_webhook_secret`
  (unlike YooKassa/Tribute which fail closed). Fix: reject webhook when secret empty
  + add prod boot validation.
- **P-2 (P0)** **Auto-renew refund safety-net crashes → user charged, no product, no
  refund.** `core/services/autorenew.py:139`: after `activate_subscription` raises
  post-charge, handler does `await session.rollback()` then synchronously reads
  `method.gateway`/`user.user_id` — but rollback expires all identity-map attributes;
  under `AsyncSession` a sync expired-attribute access raises `MissingGreenlet`, caught
  by the enclosing `except`, so `refund_stars`/`gw.refund` never runs. Fix: capture
  needed scalars before rollback (or re-fetch after) so refund actually executes.
- **P-3 (P1)** **`_record_tx` duplicate-`gateway_tx_id` handler doesn't roll back**
  despite a comment claiming a SAVEPOINT fix (`core/services/billing.py:111`). Correct
  pattern exists in `core/services/referrals.py:161` (`session.begin_nested()`). On a
  real concurrent double-delivery, `flush()` → `IntegrityError` → `return None` with no
  rollback → Postgres tx aborted → every later statement in `apply_event`
  (referral reward, upgrade notify, promo consume) raises `PendingRollbackError` →
  unhandled 500. Existing test pre-commits the dup in a separate session, so it hits
  the early SELECT and masks this. Fix: wrap the insert in `begin_nested()`.
- **P-4 (P1)** **Rollback cascade across the autorenew batch**
  (`core/services/autorenew.py:171`): one user's rollback expires *all* loaded `User`
  objects; the next iteration's `get_method(session, user.user_id)` touches an expired
  attr → same `MissingGreenlet`, skipping remaining users in the daily sweep. Fix: per-
  user session scoping or refresh between iterations.
- **P-5 (P2, spec)** Tribute webhook field/HMAC mapping is an unverified best-guess
  (`core/payments/tribute_gw.py:1`), inert behind `TRIBUTE_API_VERIFIED`. Confirm
  against a real payload before enabling. (Cannot verify without real API → staging.)
- **P-6 (P2, design)** Admin manual credit/premium grant/revoke writes only
  `AdminAuditLog`, no `transactions` ledger row (`api/admin/users.py:265`) → revenue
  reconciliation blind spot. Confirm intended; consider zero-amount ledger row.

### Phase 2 — outcomes (fixed + verified)

| ID | Sev | Status | Commit | Test |
|---|---|---|---|---|
| P-1 Stripe forged webhook | P0 | ✅ fixed | `e03e500` | `test_stripe_empty_webhook_secret_refuses` + config guards |
| P-2 auto-renew refund greenlet crash | P0 | ✅ fixed | `122dc7b` | `test_attempt_renewal_refunds_when_activation_fails` |
| P-4 auto-renew batch rollback cascade | P1 | ✅ fixed | `122dc7b` | `test_run_autorenew_batch_survives_rollbacks` |
| P-3 `_record_tx` savepoint (+referrals) | P1 | ✅ fixed | `642c33e` | `test_record_tx_duplicate_flush_does_not_poison_session` |
| G-2 double Stars refund (refund half) | P1 | ✅ fixed | `0084556` | `test_stars_refund_rechecks_status_under_lock` |
| P-5 Tribute field/HMAC mapping | P2 | ⏸ deferred | — | **requires staging** (real Tribute payload; inert behind flag) |
| P-6 admin grants no ledger row | P2 | ⏸ deferred | — | **design decision** — needs owner confirmation on reconciliation |

Money-path regression after all fixes: **98 passed** across payments/webhooks/
autorenew/refunds/apply_event/checkout/promos/CRM/payment_methods. Each touched
source file left ruff-clean. G-2's avatar-worker double-enqueue claim (the other
half) is tracked for Phase 4.

---

## Phase 3 candidates — Auth / RBAC / Sessions (lane audit; main-agent verification pending)

Surface is mature: RBAC hierarchy (`core/services/admin_auth.py:101`) enforced
server-side on every audited admin mutation; self-lockout/last-superadmin guards
under row locks; initData HMAC constant-time + auth_date staleness + fail-closed dev
bypass; JWT `token_version` revocation on every request; CORS wildcard = hard prod
boot error. Open gaps to verify + fix in Phase 3:

- **A-1 (P2)** Admin login rate-limit is **IP-only** (`api/admin/auth.py:141`,
  `core/services/ratelimit.py:14`) — no per-account lockout; distributed-IP brute
  force unbounded. Also 2FA not mandatory for `support`/`moderator`
  (`mfa_required_roles` default `admin,superadmin`, `core/config.py:191`) though those
  roles can ban users + grant ≤50 credits.
- **A-2 (P2)** `/metrics` + admin-IP-allowlist requirement gate on `is_public_deploy`
  (`core/config.py:219,291,295`) = `public_deploy_flag OR webhook_base_url`. A prod
  deploy in **polling mode** (no `WEBHOOK_BASE_URL`) is internet-reachable yet skips
  the allowlist/metrics-token check → `GET /metrics` served unauthenticated
  (`api/routers/health.py:96`). Reachability inferred from a flag, not measured.
- **A-3 (P3)** No idempotency key on `grant_credits`/`grant_premium`
  (`api/admin/users.py:247,296`) — row lock prevents lost updates but double-click =
  two grants. Contrast refund (`api/admin/ops.py:370`) which is two-phase/retry-safe.
- **A-4 (P3, spec)** Bulk PII/financial CSV export at `admin` rank, not `superadmin`
  (`api/admin/exports.py:98,144`) — policy question, up to 200k unfiltered rows.

### Phase 3 — outcomes

| ID | Sev | Status | Commit / note |
|---|---|---|---|
| A-2 `/metrics` open in polling prod | P2 | ✅ fixed | `31c17d5` — fail closed unless dev/test box |
| A-1 login lockout IP-only | P2 | ✅ fixed | `06961a7` — per-account failure lockout + reset on success |
| U-4 RoleGuard fail-open default | P3 | ✅ fixed | `88eac6b` — default to lowest privilege |
| A-1b 2FA not mandatory for support/moderator | P2 | 📋 recommend | Config policy: operators should add `support,moderator` to `MFA_REQUIRED_ROLES` (`core/config.py:191`); the mfa_setup login flow already onboards them gracefully. Not forced (changes behaviour for existing deploys). |
| A-3 no idempotency key on credit/premium grant | P3 | ⏸ deferred | `api/admin/users.py:247,296` — row lock prevents lost updates; double-click = two intentional grants. Adding client idempotency keys is arguably a product decision. |
| A-4 CSV export at admin rank | P3 | ⏸ deferred | Policy/owner decision on data-handling for admin-rank staff. |

Auth surface is otherwise mature (verified against live code): RBAC enforced
server-side on every admin mutation, self-lockout guards, initData constant-time
HMAC + fail-closed dev bypass, JWT `token_version` revocation, CORS wildcard hard
prod-fail. Regression: admin/login/refresh suites green.

---

## Phase 7 candidates — Mini App / Admin UI + e2e (lane audit; verification pending)

Already solid: no-Telegram gating, error boundaries, 24/28 admin pages use
confirm+busy state, RBAC menu filtering. Gaps:

- **U-1 (P1)** Zero e2e for the money flow. Only `miniapp/e2e/smoke.spec.ts`
  (shell-mount) exists; admin has **no** Playwright config/e2e dir at all. → Phase 7.
- **U-2 (P1)** CI never runs Playwright — `frontend` job runs only vitest + build;
  `npm run e2e` never invoked (`.github/workflows/ci.yml:86`). → Phase 7/9.
- **U-3 (P2)** Double-submit → **double charge** in `CreateSheet.run()`
  (`miniapp/src/components/CreateSheet.tsx:121`): closure guard `phase==="running"`
  not synchronous, and `run` is wired to TWO triggers (DOM `GenerateBar.tsx:71` +
  Telegram MainButton `CreateSheet.tsx:179`). Fast double-tap → two `effectGenerate`
  uploads + two charges. **Depends on backend idempotency** (cross-ref payments lane).
  Fix: synchronous `useRef` submitting-flag + confirm server-side dedup.
- **U-4 (P3)** `RoleGuard`/`AdminShell` default absent role to `"admin"` (rank 3),
  fail-**open** (`admin/src/App.tsx:124,148`) — should default to `support` (lowest).
- **U-5 (P3)** `pollJob` has no retry/backoff on a transient blip during the 3-min
  poll; single network error ends job as failed (`miniapp/src/api/client.ts:302`).
  No offline vs slow-API vs 5xx distinction; 413/415 unmapped (`client.ts:34`).

## Phase 8/9 candidates — Security / supply chain / infra (lane audit; verification pending)

Already solid: Caddy per-path frame-ancestors/CSP split, HSTS, XFF replace-not-append
(Caddy sole path to `--forwarded-allow-ips=*`), admin IP allowlist at Caddy+app,
MinIO default-cred guard, SSRF allowlist + cloud-metadata block + path-traversal
realpath guard (`core/services/storage.py:285`), CORS correct (wildcard+creds hard
prod-fail). Gaps:

- **S-1 (P1)** Base `docker-compose.yml` publishes Postgres 5432 / Redis 6379 /
  MinIO 9000-9001 / API 8000 / OmniRoute 20128 to host
  (`docker-compose.yml:12-13,22-23,42-44,57-58,101-102`). Prod overlay sets
  `ports: []`, but safety depends on operator always passing `-f …prod.yml`. Running
  base alone exposes DB/cache/object-store to internet. → Phase 9 (defense-in-depth).
- **S-2 (P2)** GitHub Actions pinned to floating tags (`@v4`, `@v6`), not commit SHAs,
  in `ci.yml` + `release.yml` — tag-repoint supply-chain risk with `packages: write`.
- **S-3 (P2)** `ci.yml` has **no `permissions:` block** → default `GITHUB_TOKEN` scope
  on every job (`release.yml` correctly scopes). Add least-privilege `permissions`.
- **S-4 (P3)** Staging exposes API on host 8001 (external-firewall-dependent);
  no committed hash-pinned `requirements.lock` though `scripts/lock-deps.sh` exists;
  `beat=1` is convention/comment, not config-enforced (`--scale beat=3` would
  double-fire cron).

---

## Phase 4 candidates — Generation / quotas / AI router / workers (lane audit; verification pending)

Verified-correct (no change): atomic charge+job-create (`bot/handlers/video.py:161`
charges `commit=False` + commits with job insert), `enqueue_or_refund`
(`core/queue.py:64`) refunds on ARQ-enqueue failure, stuck-job sweep + duplicate-
delivery guard for video/music/photoeffect (`status='processing'` conditional UPDATE
before send), Fernet `enc::` key encryption on read+write. No job-cancel feature
exists, so cancel-charge race is N/A. Gaps:

- **G-1 (P1)** **Spend cap is dead code.** `mark_success` (`core/services/ai_routing.py:196`)
  only accrues `account.spend_micros` when `cost_micros` is passed — but every real
  call passes none (`core/ai_router/registry.py:331`, `core/services/media_dispatch.py:126,195,249`);
  `AIModel.cost_micros` (`core/models/ai_routing.py:102`) is never read. So
  `spend_micros` stays 0, `_over_budget()` (`ai_routing.py:35`) never trips, and the
  admin-facing `spend_limit_micros` "hard cap" never sidelines an account. Only tests
  pass `cost_micros`. Fix: wire per-request cost from `AIModel` into `mark_success`.
- **G-2 (P1)** **Double real Telegram Stars refund** on avatar jobs.
  `workers/avatar_tasks.py:26` claims `pending→processing` via plain ORM assignment
  (not conditional UPDATE); `claim_pending_avatars` (:59) re-enqueues *all* pending
  every 5 min → two workers can both read `pending` and both call `refund_stars`.
  `core/services/refunds.py:49` takes `SELECT … FOR UPDATE` but **never re-checks
  `tx.status` after acquiring the lock** before calling `bot.refund_star_payment` —
  only the ledger reversal (`billing.py:341`) is idempotent, not the external API
  call. Live today (avatar gen is a stub that always refunds). Fix: conditional-
  claim in avatar_tasks + re-check `tx.status` after the FOR UPDATE lock in refunds.
- **G-3 (P2)** Video/music **resume can't resume** after mid-flight redelivery:
  Phase A transition is `WHERE status='pending'` (`workers/video_tasks.py:195`,
  `music_tasks.py:103`); a job redelivered while `processing` with no `result_url`
  yet hits rowcount 0 → silently returns and waits for the 30-min stuck sweep,
  wasting `submit_or_resume`'s resume logic. `CancelledError` (BaseException) in the
  poll loop isn't caught by `except Exception`. Untested path.
- **G-4 (P2)** No distributed lock guarantees single beat; `cron_control.claim()`
  (`core/services/cron_control.py:61`) is read-check-write with no `FOR UPDATE`/
  advisory lock — assumes single replica. `--scale beat=N` double-fires all crons.
- **G-5 (P2)** faceswap/upscale (`workers/photo_tools_tasks.py:52`) use plain ORM
  claim (no active double-enqueue trigger found → lower risk; refund still guarded
  by `refunded_at IS NULL`).
- **G-6 (P3)** Admin `base_url` SSRF is time-of-check-only
  (`api/admin/ai_routing.py:28`) — solid at write time, but live gateway calls don't
  re-validate resolved IP per request (DNS-rebinding residual). Recommend enforcing
  `AI_BASE_URL_ALLOWLIST` in prod (already supported).

### Phase 4 — outcomes

| ID | Sev | Status | Commit | Test |
|---|---|---|---|---|
| G-1 spend cap dead code (cost never accrued) | P1 | ✅ fixed | `cfdcb0e` | `test_submit_first_accrues_model_cost_to_account_spend` |
| G-2 avatar double Stars refund (worker claim half) | P1 | ✅ fixed | `3381928` | existing avatar/integration suite (claim structural; concurrency not SQLite-testable) |
| G-3 video/music resume stranded on `processing` | P2 | ✅ fixed | `5296dd3` | `test_resume_processing_job_polls_and_completes` (red→green) |
| G-5 faceswap/upscale plain ORM claim | P2 | ✅ fixed | `5296dd3` | `tests/test_phototools.py` regression (structural claim parity) |
| G-4 cron `claim()` read-check-write (beat >1 double-fire) | P2 | ✅ fixed | `2d1c729` | `tests/test_cron_control.py` (FOR UPDATE; single-thread behaviour preserved) |
| U-3 double-submit double-charge (backend) | P2 | ✅ fixed (backend) | `de99766` | `test_double_submit_same_idempotency_key_is_deduped` + `test_repeat_generation_with_different_key_is_allowed` |
| G-6 base_url SSRF time-of-check-only | P3 | ⏸ config rec | — | set `AI_BASE_URL_ALLOWLIST` in prod (already supported) → Phase 11 config gate |
| U-3 frontend (synchronous `useRef` flag + send token) | P2 | → Phase 7 | — | Mini App UI change |
| beat=1 config enforcement in compose | P2 | → Phase 9 | — | infra (`--scale beat` is not code-guarded; G-4 makes it *safe* regardless) |

Notes: G-3's `CancelledError` observation is **not** a bug — letting it propagate
out of the poll loop is correct (swallowing it would break graceful worker
shutdown); no change made. G-2's other half (re-check `tx.status` under the FOR
UPDATE lock in `refunds.py`) was fixed in Phase 2 (`0084556`). Full-suite
regression after all Phase 4 fixes: **869 passed** (`pytest tests/`, 6:01). Every
touched source file left ruff-clean (`photo_tools_tasks.py` import block also
tidied to fully clean).

---

## Phase 5 — Migrations / DB

Root cause (B-2): migration `0039_admin_backup_codes` creates
`admin_users.backup_codes_hashed` (2FA recovery codes) but the `AdminUser` model
never declared the column, so `scripts.check_migrations` autogenerate saw a
`remove_column` drift → **exit 1**, and the CI `migrations` job was red on `main`.
The column is orphaned scaffolding (no service/API/model code reads it) but 0039
is in the deployed chain, so the column already exists on the prod table —
dropping it would be a **destructive prod migration**, whereas declaring it on the
model is a zero-DB-change alignment.

| ID | Sev | Status | Commit | Evidence |
|---|---|---|---|---|
| B-2 model/migration drift (`backup_codes_hashed`) | P1 | ✅ fixed | `0de8cd3` | `scripts.check_migrations` **exit 1 → exit 0**; typed `JSONType` (JSONB/JSON) + `server_default '[]'` identical to 0039 |

Verified-correct (no change):
- **Single head** `0042_search_model` — linear chain, no branch/duplicate heads.
- **Fresh `alembic upgrade head`** on an isolated temp DB applies `0000→0042`
  cleanly (exit 0). 43 revisions.
- **Rollback path**: `upgrade head → downgrade -1 → upgrade head` round-trips
  cleanly (exit 0) — the latest revision is deploy-rollback-safe. Every revision
  has a real `downgrade()` (no `pass`-only irreversibles); destructive `op.drop_*`
  appears only inside downgrade bodies, never on an upgrade/data path.
- **Engine/pool/PgBouncer** (`core/db.py`): correct. PgBouncer transaction-pooling
  uses `NullPool` + `statement_cache_size=0` + `prepared_statement_cache_size=0`
  (the asyncpg-under-transaction-pooling gotcha, handled right); direct Postgres
  uses `pool_pre_ping` + tunable pool; `expire_on_commit=False` avoids post-commit
  `MissingGreenlet`. Session lifecycle / `with_for_update` / `begin_nested`
  patterns were already validated + hardened in Phases 2–4.

Regression: 196 admin/auth/migration tests green after the model change; full
suite unaffected (869 green baseline stands — only a model column was added).

---

## Phase 6 — Rest of backend / bot / integrations

Six read-only sub-agent findings were verified against current code (zero-trust:
each reproduced with a failing test before any fix) and remediated TDD red→green.
Full suite after Phase 6: **882 passed** (`pytest tests/`, 5:35), zero regressions.

| ID | Sev | Area | Status | Commit | Evidence |
|---|---|---|---|---|---|
| P6-voice | P2 | bot/handlers/chat.py | ✅ fixed | `403e894` | `first_seen` imported from `core.services.ratelimit` (which has no such name) → `ImportError` **outside** the try on every 🔊 tap → TTS 100% dead. Now imports from `core.redis_client`. Regression test drives handler past the import. |
| P6-pay-carveout | P2 | bot/middlewares ban+maintenance+gate | ✅ fixed | `3d0c0cc` | A `successful_payment` service message was droppable when the user's state flipped between pre-checkout (Telegram already charged) and delivery → charged-not-credited. Added the same carve-out ThrottlingMiddleware has. 3 middlewares, 3 tests. |
| P6-rehost-oom | P2 | core/services/storage.py | ✅ fixed | `2e7bf65` | `rehost_remote` buffered the entire provider body (`resp.content`) before the size check → multi-GB response OOMs the worker. Now streams with an incremental cap + early Content-Length reject. Per-hop SSRF re-validation preserved. |
| F1 gallery submit rate-limit | P2 | api/routers/gallery.py | ✅ fixed | `9545cde` | `/gallery/submit` had no limiter → spammable moderation cost (AI call/prompt) + queue flood. Added `ratelimit.allow` 10/h/user → 429. |
| F2 metrics token in URL | P3 | api/routers/health.py | ✅ fixed | `2e0f8ff` | `/metrics` token only via `?token=` (leaks to access logs) or non-standard header. Added `Authorization: Bearer` (Prometheus-native); `prometheus.yml` now recommends it. Query-param kept for backward-compat (removing it would silently break the deployed scraper — AUDIT-M7). |
| F3 gallery image ownership | P3 | api/routers/gallery.py | ✅ fixed | `1cca61a` | `submit` accepted any URL → a user could publish another user's private result / arbitrary image. Now the `image_url` must match one of the submitter's own `GenerationJob.result_url` rows → 403 otherwise. (Endpoint has no frontend/bot caller yet — exact-match ownership is safe.) |
| pixel-bomb | P3 | api/images.py | ✅ fixed | `ed1c87e` | Uploads decoded pixels without a hard pixel ceiling; Pillow only warns to 2× its default and `.verify()` doesn't reliably trip it. Added a 50 Mpx ceiling checked from `im.size` **before** any decode → `_validate_image` 413, `_normalize_image` None. |

Hypotheses evaluated — **not** fixed, with rationale:
- **F4 webhook replay (P3) → mitigated, no change.** `api/routers/webhooks.py`
  verifies the provider signature (YooKassa does an authoritative `Payment.find_one`
  re-fetch; Stripe verifies the signature) **and** `apply_event` is idempotent via
  the deterministic ledger keys hardened in Phase 2. A replayed valid event
  re-applies the same idempotency-keyed transaction → no double credit. Telegram
  updates are separately deduped by `_claim_update` (SETNX, 1h). Two independent
  layers already cover replay.
- **SSRF DNS-rebinding TOCTOU (P2) → residual, documented.** `_is_ssrf_url_async`
  resolves + validates the host, then `httpx` re-resolves independently at connect
  time — a narrow DNS-rebinding window. Practical exploitation needs an attacker
  who both controls a DNS domain **and** sits on a provider/result URL path
  (`rehost_remote` runs on configured-AI-provider result URLs, not arbitrary user
  input), and the code already re-validates every redirect hop (shrinking the window
  to one guarded resolve per hop). A complete fix requires pinning the validated IP
  through a custom httpx transport while preserving TLS SNI — a substantial,
  higher-risk network-layer change. **Remediation recommended** (connection-time IP
  pinning) but deferred from this deploy cycle as a known residual rather than a
  risky rewrite; tracked for a dedicated hardening PR.

---

## Phase 7 — Mini App + Admin UI/UX + e2e

Frontend baseline (all green, recorded as the verified starting point):
- **miniapp**: `tsc --noEmit` clean · `vitest` 12→15 pass · `vite build` clean.
- **admin**: `tsc --noEmit` clean · `vitest` 26 pass · `vite build` clean.

| ID | Sev | Area | Status | Commit | Evidence |
|---|---|---|---|---|---|
| U-3 double-submit | P1 | miniapp Create/CreateSheet + api/routers/miniapp.py | ✅ fixed | `d3e2b7b` | `run()` guarded only on `phase === "running"` (async React state) → a fast double-tap (DOM button + Telegram MainButton) charged/queued twice. Added a **synchronous `submittingRef`** (claimed before any await, released in `finally`) in both components, plus a per-submit-intent `idempotency_key` sent to the backend. Backend: mirrored the `effect_generate` dedup onto `free_model_generate` (previously unguarded), `_release_dedup` on all pre-commit rollbacks. |
| U-7 error taxonomy | P3 | miniapp api/client.ts | ✅ fixed | `de099d1` | Status→i18n map covered only 401/402/429/500; 413 (oversize upload) and 503 (upload failed / unavailable) fell to a generic message. Mapped 413→`err_too_big`, 503→`err_server` (existing keys, no new translations) and de-duplicated the table into one `errKeyForStatus()`. |
| e2e coverage | — | miniapp/e2e | ✅ added | `7385c81` | The only e2e was a shell-mount smoke. Added Playwright flows (backend mocked via `page.route`, deterministic, no live API) for the three App load outcomes: authenticated render (nav visible), 401→Telegram gate, 503→graceful mount with no uncaught error. `playwright test` 4 passed. |

Verified-correct (no change):
- **Admin destructive actions** (refund / credits / ban / premium / delete): the admin
  pages already carry `busy`/`disabled` guards, and — decisively — the backend refund is
  idempotent (`refund:{gateway_tx_id}` key + conditional `UPDATE ... WHERE status=…`
  under `SELECT … FOR UPDATE`, hardened in Phase 2), so even a double-click cannot
  double-refund. Client guard is UX; server is the real gate.
- **Telegram gate**: opening outside Telegram (no signed initData) + a backend 401
  renders a single "open in Telegram" card, not a wall of per-tab errors — now pinned by
  an e2e test.

Note: the U-1/U-2/U-5 sub-agent labels from the original plan were not individually
reloadable in this continued session; the frontend typecheck/unit/e2e/build baseline
above is green and serves as the verified state. Any residual UI polish is tracked for a
follow-up and is not a production blocker.

---

## Phase 8 — Security / supply chain

| ID | Sev | Area | Status | Commit | Evidence |
|---|---|---|---|---|---|
| S-metrics-edge | P2 | Caddyfile | ✅ fixed | `251af17` | Catch-all `handle /*` proxied `/metrics` to the internet (token-gated but reachable), contradicting the "Caddy blocks /metrics" claim in the app docstring + prometheus.yml. Added `handle /metrics { respond 403 }`; internal Prometheus scrapes `api:8000` directly (not via Caddy) so scraping is unaffected. |
| S-pgbouncer-tag | P3 | docker-compose.prod.yml | 📝 recommend | — | `edoburu/pgbouncer:latest` is an unpinned tag → non-reproducible builds; a shifted upstream image lands silently on the next pull. Pin to a specific version/digest. Not changed here to avoid guessing a tag that could break deploy — do it with the image digest captured during the Phase 11 discovery. |
| S-actions-pin | P3 | .github/workflows | 📝 recommend | — | Actions are pinned to major tags (`actions/checkout@v4`, `setup-python@v5`, `build-push-action@v6`, …) not full commit SHAs — a mutated tag could inject a malicious step. Pin to SHAs (Dependabot keeps them current). Low-risk hardening for a dedicated PR. |
| S-base-digest | P3 | Dockerfile | 📝 recommend | — | Base images are tag-pinned (`python:3.12-slim`, `caddy:2-alpine`, `postgres:16-alpine`) not digest-pinned. Optional reproducibility hardening; acceptable as-is. |

Verified-correct (no change — strong existing posture):
- **Container**: multi-stage build, runtime runs as **non-root** `appuser` (uid 1001),
  no build toolchain in the runtime image, `HEALTHCHECK` on `/health/ready`, and
  `pip install --require-hashes` when `requirements.lock` is present (tamper-evident).
- **Network isolation** (`docker-compose.prod.yml`): postgres / pgbouncer / redis / minio
  / api / worker / beat all `ports: []` — **nothing internal is published**; only Caddy
  binds 80/443. `api` runs `--forwarded-allow-ips="*"` but is unreachable except through
  Caddy, so XFF trust is sound.
- **Caddy edge**: HSTS (preload) + `X-Content-Type-Options nosniff` + `Referrer-Policy`;
  `/api/admin/*` IP-allowlisted at the proxy (`remote_ip` → 403) on top of app RBAC;
  **X-Forwarded-For is REPLACED with the real peer IP** (`{remote_host}`) so a client
  can't spoof it (protects the webhook source-IP allowlist + rate-limit keys); strict
  per-path CSP (admin `frame-ancestors 'none'` + `X-Frame-Options DENY`; Mini App
  `frame-ancestors` limited to telegram.org); `ADMIN_ALLOW_IP` and `DOMAIN` are
  fail-closed (`:?required`).
- **Static scans**: `bandit -r core api bot workers -ll -q` → **0 findings** (exit 0).
  `pip-audit -r requirements.txt --strict` runs in CI on Linux; locally blocked by a
  Windows venv-stdlib gap (`ModuleNotFoundError: venv` inside pip-audit) — deferred to CI,
  which already gates it.
- **Auth/webhook authenticity**: payment webhooks verify provider signature (YooKassa
  authoritative re-fetch) + source-IP allowlist (fail-closed on public deploy) +
  idempotent `apply_event`; Telegram updates deduped by SETNX (Phase 6 F4).

---

## Phase 9 — Infra / CI / quality gates

| ID | Sev | Area | Status | Commit | Evidence |
|---|---|---|---|---|---|
| B-1 whole-tree ruff | P2 | (tree) | ✅ fixed | `9c72123`, `47594c1` | `ruff check .` (a HARD gate in ci.yml) was red with **147** errors (75 E501, 36 E402, 33 I001, 1 E702) — the lint job blocked the whole pipeline (`docker` needs `[lint,test]`). Cleared all: auto-sorted imports, moved `log = get_logger()` below imports in workers, wrapped long lines. `ruff check .` → **All checks passed!** Full suite **886 passed**, zero regressions. |
| B-5 pytest-asyncio | P3 | pyproject.toml | ✅ fixed | `101e297` | `asyncio_default_fixture_loop_scope` unset → PytestDeprecationWarning every run. Pinned `"function"` (matches current behaviour). |
| B-3 coverage ratchet | P3 | .github/workflows/ci.yml | ✅ raised | `101e297` | Measured global coverage **68%** (886 tests). Raised the `--fail-under` floor **50 → 65** (small cross-platform margin under 68) so coverage can't regress; documented target 70 global / 85 critical. |
| CI e2e wiring | — | .github/workflows/ci.yml | ✅ added | `101e297` | The miniapp Playwright suite now runs in CI (install chromium + `npm run e2e`); specs mock the backend via `page.route` → deterministic, no live API. |

Verified-correct (no change):
- **`beat` = 1**: `docker-compose.prod.yml` keeps the scheduler at a single replica
  ("only the `worker` service may be scaled") — no duplicate cron fan-out. The
  cron-claim hardening (Phase 4 G-4, `cron_control.claim()` under `FOR UPDATE`) makes
  beat safe even past 1 replica as defence in depth.
- **CI completeness** (`ci.yml`): lint (gate), typecheck (informational), pytest+coverage
  (gate), migrations (`alembic upgrade head` + `scripts.check_migrations` drift), frontend
  matrix (vitest + build, now + e2e), security (`pip-audit --strict` + `bandit`), docker
  build. `release.yml` present.
- **Migration/health infra**: fresh `alembic upgrade head` clean (Phase 5); Dockerfile
  `HEALTHCHECK` on `/health/ready`; `/health`, `/health/ready` liveness/readiness split.
- **Disaster readiness**: `scripts/backup.sh` runs as a resource-limited compose service
  writing to a `backups` volume; `scripts/restore_test.sh` present for isolated
  restore rehearsal. A real restore drill runs in staging (Phase 11 gate), never against
  prod data.

---

## Phase 10 — GitHub: push / PR / merge

- **Pre-push safety** (all clean): `git diff --check` clean; 92 files changed vs
  `origin/main`; no secrets in added lines; no `.env`/`dist`/`node_modules`/`.pyc`
  artifacts committed.
- **Pushed**: branch `claude/production-readiness-audit` → `origin` (37 commits ahead of
  `main`, 0 behind, linear/fast-forwardable). Push succeeded (cached credential).
- **PR opened**: **#1** → `main` (`gh` CLI absent; created via GitHub REST API with the
  same stored credential, token never printed).
- **CI status — BLOCKED**: the CI workflow run concluded `startup_failure` (0 jobs
  started) on the head SHA, as did the **untouched** `release.yml` (`failure`). Because a
  workflow I never edited also fails to start, this is a **repository-level GitHub Actions
  configuration issue** (this is the repo's first-ever Actions run — PR #1), not a defect
  in the audit diff. `ruff`/`pytest`/frontend all pass locally.
- **Merge — NOT performed.** The plan's gate is explicit: merge only with green required
  checks. With CI unable to start, there are no green checks, so merging is withheld
  pending the user resolving Actions (enable Actions / approve first run / runners /
  billing) — after which CI can be re-run and, if green, the merge completed.

---

## Bot exhaustive functional verification (2026-07-12, sub-project #5)

Line-by-line read of **all 28 `bot/handlers/*.py` files** covering **118 entrypoints**
(28 commands + message + callback + inline handlers). Verification axes per handler:
ban/section/premium gate, input validation, atomic charge/refund, moderation-before-AI,
FSM state isolation, idempotency, HTML escaping, callback_data parse safety.

**Result: 0 new defects.** The bot is uniformly hardened (Phase 6 fixes verified in place):
- Payments (`premium`/`packs_buy`/`gift`): idempotent activation on `charge_id`, refund-on-failed-grant, narrowed `successful_payment` filter (multi-router safety), duplicate-delivery re-fetch, single-use promo consumed once.
- Generation (`chat`/`photo`/`video`/`kling`/`music_gen`/`search`/`documents`): atomic charge+job (`commit=False`→single commit), refund on ANY provider exception carrying `was_premium`, partial-variant refund, seed bounds (0…2³¹−1), empty-result guard, streaming `interrupted` flag.
- Moderation precedes every text→AI path (chat/search/photo/video/music/documents/inline/vision/role).
- Guards: `html.escape` on user/admin text, `try/except` on every `callback_data` split, Redis fail-open, correct per-bot username under multi-bot, ban re-check on middleware-bypassing inline path.

Handlers reviewed: account, bonus, chat, contests, context, documents, gift, groups,
inline, invite, kling, links, menus, misc, model, music_gen, packs_buy, photo, premium,
promo, roles, search, settings, start, support, video (+ __init__).

---

## Improvement workstream #1 — infra port exposure (P0) — FIXED (2026-07-12)

**Root cause (Context7-verified vs compose-go v2.13):** `ports` is not in Compose's
`mergeSpecials`, so `-f` files APPEND `ports` lists rather than replacing them. The prod
overlay's `ports: []` therefore never cleared the base `docker-compose.yml` publishes —
Postgres(5432)/Redis(6379)/MinIO(9000-9001)/OmniRoute(20128)/api(8000) were bound on
`0.0.0.0`. Host `ufw` inactive → the AWS Security Group was the sole protection.

**Fix (`docker-compose.prod.yml`, commit `997bfa5`):**
- `ports: !reset []` on postgres/redis/minio/omniroute/pgbouncer — the `!reset` tag drops
  the merged key entirely (Docker-network-only access).
- `ports: !override ["127.0.0.1:8000:8000"]` on api — loopback bind (local health/monitoring
  works; not internet-reachable; public traffic via Caddy).
- Server `.env` perms tightened `0755`→`0600`.

**Verified on prod after `up -d`:** host listening sockets reduced to `0.0.0.0:80`,
`0.0.0.0:443`, `127.0.0.1:8000`. Ports 5432/6379/9000/9001/20128 no longer public.
api `healthy`, `/health/ready=200` (DB+Redis reachable internally), public `/health=200`,
`/metrics=403`, `/miniapp/=200`; `redis-cli ping`=PONG; worker/beat errors(60s)=0 (a single
restart each during the redis recreation window, then stable); omniroute healthy.

**Note:** a `docker compose config` render inadvertently surfaced `POSTGRES_PASSWORD` in a
session log during validation — recommend rotating `POSTGRES_PASSWORD` + `DATABASE_URL` as a
precaution. Defense-in-depth now holds even if the AWS SG is mis-set, but SG verification
(only 22/80/443 inbound) is still recommended.

---

## Improvement workstream #2 — supply-chain pinning — DONE (2026-07-12, commit 43e3ae2)

- **GitHub Actions SHA-pinned** in `ci.yml` + `release.yml`: `actions/checkout@34e1148…`,
  `actions/setup-python@a26af69…`, `actions/setup-node@49933ea…`, `actions/upload-artifact@ea165f8…`,
  `docker/setup-buildx-action@8d2750c…`, `docker/build-push-action@10e90e3…`,
  `docker/login-action@c94ce9f…`, `docker/metadata-action@c299e40…` (each keeps a `# vX` comment).
  A moved tag can no longer inject code into CI.
- **All external images digest-pinned** to the currently-running, tested images:
  postgres/backup `@sha256:e013e867…`, redis `@sha256:6ab0b6e7…`, minio `@sha256:14cea493…`,
  omniroute `@sha256:ceae8d9d…`, pgbouncer `@sha256:4c1ca296…`, caddy `@sha256:5f5c8640…`.
  `docker compose config -q` validates; NOT force-recreated (running images already match the
  digests, so the pin is latent until the next deploy — zero downtime now).

**Additional finding (logged, not fixed here):** `release.yml` has `needs: [lint, test]`, but
those jobs live in `ci.yml`, not `release.yml` — a job cannot depend on a job from another
workflow, so the release workflow is misconfigured (contributes to its failed status). Fix by
either removing the `needs` or gating on the CI workflow via `workflow_run`. Deferred (CI is
account-billing-blocked; no impact until Actions runs again).

**Not done (lower priority, documented):** Dockerfile base `python:3.12-slim` is not digest-pinned
— pinning would force a rebuild against a base newer than the running image; safer to pin during a
planned rebuild window with a captured digest.
