# Final merge / deploy gate — claude/loop-engineering → main → AWS

Single consolidated go/no-go for the Loop Engineering branch. **Merge and deploy are HELD for
explicit owner confirmation** (per instruction). GitHub CI is not bypassed — it is blocked at the
account level (see F1); `scripts/ci_local.sh` is the adopted temporary merge-gate.

## What's in the branch (delta vs `main`)
- **Production-relevant (deploy changes the schema):** migrations `0043_users_bot_id_index` +
  `0044_missing_model_indexes` — 4 additive indexes closing model↔migration drift (F2/F3).
- **Tests only (NOT shipped in the Docker image):** ~20 new `tests/test_*.py` files (money/auth
  critical-domain coverage) + Admin Playwright e2e harness (`admin/playwright.config.ts`,
  `admin/e2e/*`) + `miniapp/e2e/responsive.spec.ts`.
- **Infra/CI:** `scripts/ci_local.sh` (local CI mirror); `.github/workflows/ci.yml` patched to
  run on a self-hosted `flashbot-ci` runner + skip the heavy docker build on this branch.
- **Docs:** `docs/loop/*`.
- Runtime application code (api/bot/core/workers) unchanged EXCEPT the two additive migrations —
  verify with `git diff --name-only main..HEAD` (migrations + tests + admin-harness + scripts +
  workflow + docs only).

## Verification status (measured, current HEAD)
- **Coverage targets MET:** global **70.36%** (10059/14296, ≥70) · critical-domain **85.2%**
  (2616/3070, ≥85). Suite **1014 passed / 0 failed** (baseline 905/68%).
- **Two independent convergence loops** — both green + reproducible: ruff clean · pytest 1014 ·
  coverage crit 85.2%/global 70.36% · bandit exit 0 · alembic single head `0044` +
  `check_migrations` no drift · miniapp (vitest 17/tsc/build/e2e 6) · admin (vitest 26/tsc/build/
  e2e 4). Manifest: 627 files / 175 test files / 983 test functions / 45 migrations.
- **`scripts/ci_local.sh` (adopted gate) fresh run on HEAD `71faa2f` — ALL BLOCKING GATES PASSED**
  (exit 0): ruff · pytest 1014 passed / coverage TOTAL 70% (ratchet 67) · alembic upgrade head +
  check_migrations no drift · bandit · miniapp (npm ci/vitest/tsc/build/e2e) · admin (npm ci/
  vitest/tsc/build). Informational only (non-blocking): ruff-format, mypy, pip-audit (venv-blocked).
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
- Runner is currently **stopped** (systemd `inactive`, still `enabled`/installed) per owner choice
  — ready to `start` the moment the account block is lifted.
- **Only the owner can unblock:** resolve GitHub billing/payment, OR make the repo public. Neither
  is doable from code. Until then, `scripts/ci_local.sh` is the gate.

## Blockers before merge (owner action)
1. **Explicit owner confirmation to merge** (no automated self-merge; the harness refuses it).
2. GitHub CI cannot run (F1). The adopted gate is `scripts/ci_local.sh` (green — see above).

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

## Recommendation
Merge is LOW risk (additive indexes + tests + workflow/docs). Deploy is a safe concurrent index
backfill. Suggested order: owner unblocks Actions (public repo or billing) OR accepts ci_local.sh
as the gate → confirm ci_local.sh green → **explicit merge confirmation** → merge PR #3 →
**explicit deploy confirmation** → deploy per runbook. Nothing proceeds without those confirmations.
