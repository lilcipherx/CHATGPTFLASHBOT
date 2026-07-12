# Loop Engineering — findings

Severity: **P0** (prod-down / money loss / auth bypass / data loss), **P1** (serious, exploitable
or user-visible breakage), **P2** (correctness/robustness, limited blast radius), **P3** (hygiene).

Each finding: flow → root cause → reproduction → fix → tests → commit → remaining risk.
Zero-trust: a "fixed" note requires a failing-then-passing test and a verified commit SHA.

---

## Resolved candidate findings (verified — dismissed as safe, no code fix needed)

### C1 (P1 candidate) — Mini App dev auth bypass reachability — DISMISSED (fail-closed)
- Flow: `api/deps.py:79` `current_webapp_user` → `DEV_WEBAPP_USER` only when
  `_dev_bypass_enabled()` (`api/deps.py:66`): `dev_webapp_bypass AND env in {dev,test} AND
  NOT is_public_deploy`.
- Verified: `is_public_deploy` (`core/config.py:219`) is true whenever `PUBLIC_DEPLOY=true`
  OR `WEBHOOK_BASE_URL` is set — the latter is present in every process's `.env` on a real
  webhook deploy (`docker-compose.prod.yml:78` `BOT_MODE: webhook`). So the standard prod
  deploy has the bypass fail-closed. Residual is only an operator explicitly setting
  `ENV=dev` + flag + polling + `PUBLIC_DEPLOY=false` in prod — a documented "hold it wrong"
  (`.env.example:25-26`), not a code defect. No fix.

### C2 (P1 candidate) — every mutating admin route must be RBAC-guarded — DISMISSED + GUARDED
- Verified via NEW introspection test `tests/test_admin_rbac_coverage.py`: walks `app.routes`,
  and for every `/api/admin/*` route except the two intentionally-public auth endpoints
  (`/auth/login`, `/auth/refresh`) asserts `current_admin` or `current_admin_enrolling` is in
  the route's dependency tree. `require_role(...)` → `current_admin` → `ip_allowlisted`, so
  this covers IP allow-list + JWT auth + RBAC in one assertion. **Test PASSES** — no unguarded
  admin endpoint exists at `bb44014`. The test is a durable regression guard against a future
  endpoint forgetting the dependency.

### C3 (P2 candidate) — JWT default secret shippability — DISMISSED (boot abort)
- Verified: `core/config.py:343 get_settings()` calls `_require_prod_secret()` and
  `settings = get_settings()` runs at module import (process startup). On any public deploy
  (`is_public_deploy`), `admin_jwt_secret == "change-me-in-prod"` raises `RuntimeError` →
  process fails to boot (`core/config.py:234`). Same guard also hard-fails empty `enc_secret`,
  `minioadmin` S3 creds, wildcard CORS, `memory://` redis, SQLite DB, missing IP
  allowlist/metrics token, and Stripe-secret-without-webhook-secret. No fix. (Existing tests:
  `tests/test_audit_fixes.py:156-198`.)

### C4 (P3) — SPA dev-dependency vulnerabilities (esbuild <=0.24.2)
- Flow: `miniapp` + `admin` each report 5 npm advisories (3 moderate / 1 high / 1 critical),
  all transitive `esbuild <=0.24.2` via vite/vitest — a dev-server SSRF class issue.
- Impact: dev-only. Production build artifacts and the deployed Caddy/SPA are unaffected.
- Fix path (security domain): either accept (dev-only) with a documented note, or bump
  vite/vitest (breaking: vitest@4). Defer to security-domain decision; not a prod risk.

### C5 (P3) — mypy debt (306 errors, non-blocking)
- Flow: `mypy core api bot workers` reports 306 errors, dominated by aiogram
  `Message | InaccessibleMessage | None` union-attr (e.g. `bot/handlers/settings.py`) and
  SQLAlchemy `ColumnElement` vs `BinaryExpression` arg-type false positives (`api/admin/ops.py`).
- CI is `|| true` so non-blocking. Not a runtime bug on its own, but hides real ones.
- Fix path: incrementally add guards/`assert msg` narrowing in the worst files; out of scope
  for a single loop — track as debt.

---

## Confirmed findings (root-caused + failing test + fix + verified commit)

### F1 (P1 ops) — GitHub Actions CI is non-functional (0 jobs / startup_failure)
- Flow: `.github/workflows/ci.yml` + `release.yml` gate the release process ("merge to main is
  CI-green"; `release.yml` relies on branch protection to enforce it).
- Verified (zero-trust, via `gh` at bb44014): EVERY recent Actions run — including Dependabot's
  — is `startup_failure` at 0s. `gh api .../actions/runs/<id>/jobs` → `total_count = 0` (no job
  ever spawns). The repo is **private** (`.private = true`) and branch protection returns HTTP
  403 "Upgrade to GitHub Pro or make this repository public" → **no branch protection is or can
  be configured on this plan**. 0-jobs + all-runs-fail is the signature of exhausted/blocked
  Actions minutes on a private free-plan repo, NOT a workflow-file bug (the YAML parses and is
  schema-valid; a real parse error would still create a run with a failed setup job).
- Impact: the CI gate the release/merge process assumes does not exist. Any "CI-green" claim in
  older audit docs is false. Merges to `main` are ungated by CI.
- Root cause: account/plan level (Actions minutes/billing on a private repo) — NOT fixable in
  code. Remediation is the owner's decision: (a) restore Actions spending limit/minutes, (b)
  make the repo public (enables free Actions + branch protection), or (c) formally adopt
  local-gate verification as the gate.
- Compensating control applied THIS loop: the full CI-equivalent gate set was run locally and is
  green (ruff, pytest 905, coverage 68%, bandit, alembic+drift, miniapp/admin vitest+tsc+build,
  miniapp e2e). Only `pip-audit` (venv-blocked locally) and `docker build` were not run locally.
- Remaining risk: until billing/public/policy is resolved, no automated gate runs on push. P1.

---
