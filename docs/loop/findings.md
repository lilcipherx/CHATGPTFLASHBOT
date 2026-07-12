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

_None yet. Loop 0 established the baseline; no P0/P1 confirmed._

---
