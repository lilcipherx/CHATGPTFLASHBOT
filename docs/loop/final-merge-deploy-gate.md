# Final merge / deploy gate — claude/loop-engineering → main → AWS

Single consolidated go/no-go for the Loop Engineering branch. Prepared after the domain loops;
merge and deploy are HELD for explicit owner action (per instruction). Nothing here bypasses CI.

## What's in the branch (delta vs `main`)
- **Production change (deploy-relevant):** migrations `0043_users_bot_id_index` +
  `0044_missing_model_indexes` — 4 additive indexes closing model↔migration drift (F2/F3).
- **Tests (not shipped in image):** `tests/test_admin_rbac_coverage.py`,
  `tests/test_migration_bot_id_index.py`, `miniapp/e2e/responsive.spec.ts`.
- **Infra tooling:** `scripts/ci_local.sh` (local CI mirror).
- **Docs:** `docs/loop/*`.
- No changes to runtime application code (api/bot/core/workers) — verified
  `git diff --name-only main..HEAD` is migrations + tests + scripts + docs only.

## Verification status (this loop, zero-trust — actual output)
- Local gates GREEN: ruff, pytest **908**, coverage **68%** (ratchet 67), bandit, alembic single
  head `0044` + `check_migrations` no drift, miniapp (vitest 17 / tsc / build / **e2e 6**), admin
  (vitest 26 / tsc / build). `pip-audit` blocked in local venv (CI-enforced); `docker build` not
  run locally.
- Domains reviewed clean (no P0/P1): L1 payments (idempotency/refund/webhook-sig), L2 auth/RBAC
  (+ guard test), L3 generation charge + workers idempotency, L4 database (F2/F3 FIXED), L5
  uploads/S3/SSRF. L6 responsive e2e added. L7 CI + AWS inventory.
- Findings: **F1** (P1 ops, CI non-functional — owner action), **F2/F3** (P2 db — FIXED),
  C1–C5 dismissed (C1/C3 empirically confirmed safe on real prod).

## Blockers before merge (owner decisions)
1. **PR #3 merge needs human review** — the harness correctly refused an agent self-merge with no
   functioning CI. Merge via GitHub UI, or authorize the merge explicitly.
2. **CI is non-functional (F1)** — a real CI-green gate is impossible until the owner restores
   Actions (billing / make repo public / self-hosted runner — see `ci-remediation.md`). Until
   then `scripts/ci_local.sh` is the compensating gate (ran green this loop).

## Merge steps (once owner approves)
1. Ensure `scripts/ci_local.sh` is green on the latest branch HEAD (or CI green if restored).
2. Merge PR #3 into `main` (no branch protection exists to bypass on the current plan).
3. Fast-forward local `main`; tag if a release image is wanted (`release.yml` runs on `v*.*.*`
   tags — but only once Actions is restored).

## Deploy steps (AFTER merge — authorized "deploy after merge")
Deploy the exact merged `origin/main` SHA via `ssh flashbot` per [[flashbot-deploy-workflow]].
This deploy DOES change the schema (0043/0044). Follow `docs/loop/migration-runbook.md`:
1. Confirm prod `alembic current == 0042` (verified read-only this loop).
2. Take + verify a fresh backup; record current deployed dir + image tags (rollback anchors).
3. Deploy; `alembic upgrade head` reaches `0044` (CONCURRENT index builds — no write lock; watch
   for INVALID index on interruption → `DROP INDEX CONCURRENTLY` + re-run).
4. Post-deploy: 4 new indexes VALID on `users`/`gifts`/`contest_entries`; `/health/ready` OK.
5. Rollback if needed: app-only rollback (old app runs fine against the indexed schema — no schema
   downgrade needed) via `.predeploy.*` snapshot; DB downgrade only if truly required.

## Recommendation
Merge is LOW risk (additive indexes + tests). The one true gap is F1 (owner must restore CI).
Deploy is a safe, concurrent index backfill. Suggested order: restore Actions (F1) → confirm
CI/`ci_local.sh` green → merge PR #3 → deploy per runbook.
