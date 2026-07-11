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
