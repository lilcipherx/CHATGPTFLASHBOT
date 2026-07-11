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
