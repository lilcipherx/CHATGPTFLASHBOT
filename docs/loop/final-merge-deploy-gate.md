# Final merge / deploy gate — claude/loop-engineering → main → AWS

## STATUS: **READY FOR MERGE WITH ACCEPTED RESIDUAL RISKS** — merge/deploy still HELD for explicit owner confirmation.
Owner has **accepted the 38 residual CVEs as temporary residual risk for this release** (no major
FastAPI / Starlette / aiogram / aiohttp upgrades now — deferred to the next security cycle, see
Follow-up FU-2). Pre-merge hardening: admin e2e PASS · Docker build NON-BLOCKING residual · pip-audit
59/97 fixed + 38 accepted residuals · mypy = baseline debt (306 pre-existing, no new). **Merge and
deploy each require a separate explicit owner confirmation** — nothing is executed automatically.

Merge and deploy are HELD for explicit owner confirmation (per instruction). GitHub CI is blocked
at the account level (F1); self-hosted runner installed then **disabled** (kept, off the prod host).

### Pre-merge hardening checks (requested)
1. **Admin Playwright e2e — PASS.** Real cmd `npm run e2e` (playwright, preview :4174). On HEAD:
   **4 passed** (login gate, login→shell, RBAC support-hides-superadmin, superadmin-sees-all).
   (This is separate from ci_local.sh, which only runs the *miniapp* e2e.)
2. **Production Docker build — NON-BLOCKING residual limitation** (owner decision). This branch does
   NOT change `Dockerfile` or the compose files. The live prod deploy config was validated read-only
   via `ssh flashbot`: `docker compose -f docker-compose.yml -f docker-compose.prod.yml config -q`
   → exit 0 (valid merge, zero secret output). Docker Desktop is not installed locally and building
   on the prod host is disallowed/disk-risky, so the image build itself is left UNVERIFIED as a
   documented residual limitation — to be built on a non-prod host / CI VM if/when available. The
   bumped deps are standard manylinux/pure wheels for `python:3.12-slim`, expected to install cleanly.
3. **pip-audit — 59 of 97 fixed + validated; 38 residual (owner decision).** Isolated pip-audit
   2.10.1 on production `requirements.txt`: 97 → fixed 59 (pillow 12.3.0, python-multipart 0.0.31,
   pyjwt 2.13.0, cryptography 48.0.1, pypdf 6.13.3 — each validated, full suite 1014 passed). The
   **38 remaining are core-framework-pinned + reachability-triaged**: `aiohttp` (30, **not reachable**
   — app runs no aiohttp server; all CVEs are server-side; pinned `<3.11` by aiogram) and `starlette`
   (8, pinned `<0.42` by fastapi; 2 are Windows-only/not-reachable, the reachable form/Range DoS need
   a starlette-1.x major bump). A fastapi 0.116.2+starlette 0.47.2 bump was validated (1014 passed)
   but reverted — it clears only 1/8 for a core-framework swap. See `docs/loop/pip-audit-triage.md`.
   No known RCE. **ACCEPTED by owner as temporary residual risk for this release.** Owner: repo owner
   (lilcipherx). Remediation target: **next security cycle — 2026-10-14** (Follow-up FU-2).
4. **mypy — BASELINE DEBT (not a pass).** Full-backend `mypy core api bot workers` = **306
   pre-existing errors**, unchanged vs origin/main (this branch changed zero backend source — only
   `migrations/` + `tests/`). CI runs mypy non-blocking (`|| true`). Tracked as baseline type-debt
   (Follow-up FU-6): this branch introduces NO new mypy errors but does not reduce the existing 306.

**HEAD: (see git log — post dep-triage)** · PR #3 `mergeable=CLEAN` · working tree clean.

## What's in the branch (delta vs `origin/main` — 37 files, verified `git diff --name-only`)
- **Production-relevant:** (a) migrations `0043_users_bot_id_index` + `0044_missing_model_indexes`
  — 4 additive indexes (F2/F3); (b) `requirements.txt` — 5 validated dependency bumps (pillow 12.3.0,
  python-multipart 0.0.31, pyjwt 2.13.0, cryptography 48.0.1, pypdf 6.13.3) fixing 59 of 97 CVEs
  (full suite 1014 passed after each). These reach the runtime image.
- **Tests only (NOT shipped in the Docker image, 20 files):** `tests/test_*.py` money/auth
  critical-domain coverage + Admin Playwright e2e harness (`admin/playwright.config.ts`,
  `admin/e2e/{auth,rbac}.spec.ts`, `admin/package.json`+lock) + `miniapp/e2e/responsive.spec.ts`.
- **Infra:** `scripts/ci_local.sh` (local CI mirror).
- **Docs:** `docs/loop/*` (8 files).
- **`.github/workflows/ci.yml`: reverted to `origin/main`** — the self-hosted-runner workaround was
  removed from the PR (the runner lived on the prod host and Actions is account-blocked anyway; a
  dedicated CI VM will host a runner if CI is restored). ci.yml is NOT in the branch delta.
- **NO production runtime code** (api/bot/core/workers) changed except the two additive migrations
  — verified: `git diff --name-only origin/main..HEAD | grep -E '^(api|bot|core|workers)/' | grep
  -v migrations/` → empty.

## Verification status (measured, current HEAD)
- **Coverage targets MET:** global **70.36%** (10059/14296, ≥70) · critical-domain **85.2%**
  (2616/3070, ≥85). Suite **1014 passed / 0 failed** (baseline 905/68%).
- **Two independent convergence loops** — both green + reproducible: ruff clean · pytest 1014 ·
  coverage crit 85.2%/global 70.36% · bandit exit 0 · alembic single head `0044` +
  `check_migrations` no drift · miniapp (vitest 17/tsc/build/e2e 6) · admin (vitest 26/tsc/build/
  e2e 4). Manifest: 627 files / 175 test files / 983 test functions / 45 migrations.
- **`scripts/ci_local.sh` (adopted gate) fresh run on HEAD `82e1d9a` — ALL BLOCKING GATES PASSED**
  (exit 0): ruff · pytest **1014 passed** / coverage TOTAL **70%** (ratchet 67) · alembic upgrade
  head + check_migrations no drift · bandit · miniapp (npm ci/vitest/tsc/build/e2e) · admin (npm
  ci/vitest/tsc/build). Informational only (non-blocking): ruff-format, mypy, pip-audit (venv-blocked).
- `pip-audit` blocked in the local venv (missing stdlib `venv`); `docker build` not run locally.
- Domains reviewed clean (no P0/P1): L1 payments (idempotency/refund/webhook-sig), L2 auth/RBAC,
  L3 generation charge + workers idempotency, L4 database (F2/F3 FIXED), L5 uploads/S3/SSRF.

## F1 — GitHub CI is account-level blocked (self-hosted does NOT bypass it)
- A repo-scoped self-hosted runner was installed on the AWS host: user `ghrunner` (uid 1001,
  non-root, not in sudo/docker), dir `/home/ghrunner/actions-runner` (isolated from prod app),
  labels `self-hosted, Linux, X64, flashbot-ci`, systemd service — verified Online/Idle.
- **Proof it's account-level:** after pushing, both `ci.yml` runs AND a trivial echo-only
  self-hosted smoke workflow produced `startup_failure` with **0 jobs**, and the runner never went
  busy. GitHub cannot dispatch ANY run. So the block is account/billing-level, not a workflow-file
  issue and not runner availability.
- Runner is now **stopped AND disabled** (systemd `is-active=inactive`, `is-enabled=disabled`) —
  will NOT auto-start on reboot. Unit file + `/home/ghrunner/actions-runner` kept intact (not
  removed). The ci.yml self-hosted patch was reverted out of the PR; a dedicated CI VM should host
  the runner if/when CI is restored (keeping CI off the production host).
- **Only the owner can unblock:** resolve GitHub billing/payment, OR make the repo public. Neither
  is doable from code. Until then, `scripts/ci_local.sh` is the gate.

## Blockers before merge (owner action)
1. **Explicit owner confirmation to merge** (no automated self-merge; the harness refuses it).
2. GitHub CI cannot run (F1). The adopted gate is `scripts/ci_local.sh` (green — see above).

## Follow-up tasks (post-release, tracked — NOT blocking this merge)
| # | Task | Owner | Target |
|---|------|-------|--------|
| FU-1 | **Restore GitHub CI** — resolve Actions billing / make repo public / stand up a dedicated CI VM, so runs dispatch again (self-hosted on the prod host was disabled and does NOT bypass the account block). | repo owner (lilcipherx) | before next feature merge |
| FU-2 | **Dependency modernization** — clear the 38 accepted residual CVEs via coordinated major upgrades: `starlette` 1.x + a supporting `fastapi`; `aiogram`→`aiohttp` ≥3.12; re-audit + full regression + e2e. | repo owner | **next security cycle — 2026-10-14** |
| FU-3 | **Image SHA labels** — add `org.opencontainers.image.revision`/`source` to the Dockerfile build so a deployed image ↔ git SHA is verifiable (currently app images carry no revision label). | repo owner | next deploy |
| FU-4 | **Off mutable `:latest`** — pin `omniroute` / `minio` / `pgbouncer` (and align long-running containers still on `:latest`) to digests; `--force-recreate` on next deploy. | repo owner | next deploy |
| FU-5 | **UFW hardening** on the AWS host — enable `ufw` (allow 22/80/443, deny rest) as defense-in-depth behind the Security Group. | repo owner | ops window |
| FU-6 | **mypy baseline debt** — pay down the 306 pre-existing `mypy core api bot workers` errors over time; tighten the CI typecheck from non-blocking toward gating. | repo owner | ongoing |

## Merge steps (ONLY after explicit owner confirmation)
1. Confirm `scripts/ci_local.sh` green on the exact HEAD being merged.
2. Merge PR #3 into `main` (no branch protection exists on the current plan).
3. Fast-forward local `main`.

## Deploy steps (ONLY after merge + separate explicit confirmation)
Deploy the exact merged `origin/main` SHA via `ssh flashbot` per [[flashbot-deploy-workflow]].
This deploy DOES change the schema (0043/0044). Follow `docs/loop/migration-runbook.md`:
1. Confirm prod `alembic current == 0042` (verified read-only earlier).
2. Fresh backup taken + verified; record deployed dir + image tags (rollback anchors).
3. `alembic upgrade head` reaches `0044` — CONCURRENT index builds (no write lock; on interruption
   `DROP INDEX CONCURRENTLY` + re-run).
4. Post-deploy: 4 new indexes VALID on `users`/`gifts`/`contest_entries`; `/health/ready` OK.
5. Rollback: app-only (old app runs fine against the indexed schema) via `.predeploy.*` snapshot.

## Residual risk (at HEAD `82e1d9a`)
- **Merge:** LOW. No production runtime code changes; the only shippable change is two additive,
  concurrent-safe indexes. Tests/harness/docs/ci_local.sh don't reach the runtime image.
- **Deploy (schema):** LOW but non-zero — `CREATE INDEX CONCURRENTLY` can leave an INVALID index if
  interrupted (recovery in `migration-runbook.md`). Backup + app-only rollback covered.
- **CI gate:** MEDIUM process risk — the merge would be gated by `ci_local.sh` (local), not GitHub
  CI, because Actions is account-blocked. `ci_local.sh` covers the same gate set except `pip-audit`
  (venv-blocked locally) and `docker build` (not run). These two are unverified until CI is
  restored on a proper runner/VM.
- **Docker image build:** UNVERIFIED locally (`docker compose build` not run). If desired before
  deploy, build once on a non-prod machine or the future CI VM.

## Recommendation
Merge is LOW risk (additive indexes + tests + docs; ci.yml back to main). Deploy is a safe concurrent index
backfill. Suggested order: owner unblocks Actions (public repo or billing) OR accepts ci_local.sh
as the gate → confirm ci_local.sh green → **explicit merge confirmation** → merge PR #3 →
**explicit deploy confirmation** → deploy per runbook. Nothing proceeds without those confirmations.
