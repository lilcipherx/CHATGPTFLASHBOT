# Loop Engineering — findings

Severity: **P0** (prod-down / money loss / auth bypass / data loss), **P1** (serious, exploitable
or user-visible breakage), **P2** (correctness/robustness, limited blast radius), **P3** (hygiene).

Each finding: flow → root cause → reproduction → fix → tests → commit → remaining risk.
Zero-trust: a "fixed" note requires a failing-then-passing test and a verified commit SHA.

---

## Open / candidate findings (from Loop 0 discovery — NOT yet root-caused or fixed)

These are hypotheses raised during discovery. They must be confirmed (or dismissed) in the
relevant domain loop before any fix. Do not treat as confirmed bugs.

### C1 (P1 candidate) — Mini App dev auth bypass reachability
- Flow: `api/deps.py:79` `current_webapp_user` returns a fixed `DEV_WEBAPP_USER` for any
  request lacking initData when `DEV_WEBAPP_BYPASS` is on AND `ENV in {dev,test}` AND not
  public deploy (`_dev_bypass_enabled`).
- Concern: a prod host misconfigured with `ENV=dev` + flag on would authenticate everyone.
- To verify (auth domain): confirm `is_public_deploy` / `_dev_bypass_enabled` is fail-closed
  and cannot be reached under the actual prod compose env. Add a regression test asserting
  bypass is refused whenever `is_public_deploy` is true regardless of ENV/flag.

### C2 (P1 candidate) — Every mutating admin route must declare require_role/current_admin
- Flow: `admin/src/App.tsx` RBAC (`RoleGuard`) is client-side UX only; backend is authoritative.
- To verify (auth/RBAC domain): enumerate all routes under `api/admin/*` and assert each
  mutating endpoint has `Depends(current_admin)` + `require_role(...)`. Build a test that
  introspects the router and fails on any unguarded mutation.

### C3 (P2 candidate) — JWT default secret shippability
- Flow: `api/admin/auth.py:449` treats `admin_jwt_secret == "change-me-in-prod"` as a
  security-score signal; `core/config.py:234` guard rejects the placeholder on public deploy.
- To verify (auth domain): confirm the boot guard actually aborts startup (not just warns)
  under public deploy, and that staging/prod compose supplies a real secret.

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
