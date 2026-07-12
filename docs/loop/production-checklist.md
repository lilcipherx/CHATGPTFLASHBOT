# Loop Engineering — production checklist

Go/no-go gates for staging + production. A box is checked ONLY with verified evidence
(command output / commit SHA / screenshot). Zero-trust: no box is checked from a doc claim.

## Local quality gates (verified @ bb44014, Loop 0)
- [x] `ruff check .` — PASS
- [x] `pytest -q` — 905 passed / 0 failed
- [x] coverage `--fail-under=67` — PASS, TOTAL 68% (14296 stmt / 4560 miss)
- [x] `bandit -r core api bot workers -ll -q` — exit 0
- [ ] `pip-audit -r requirements.txt` — BLOCKED locally (venv module missing); rely on CI
- [x] `alembic upgrade head` + `check_migrations` — PASS, no drift, single head 0042
- [x] miniapp: vitest 17 / tsc clean / build / e2e 4 passed
- [x] admin: vitest 26 / tsc clean / build
- [ ] `docker compose build` — not yet run locally (ops domain)
- [ ] mypy — 306 errors (non-blocking); tracked as debt

## CI / GitHub (to verify in ops domain)
- [ ] GitHub Actions billing restored + CI green on `claude/loop-engineering` PR
- [ ] Branch protection on `main` requires CI checks (lint/test/migrations/frontend/security/docker)
- [ ] Release workflow builds+pushes GHCR image on tag

## Security posture (to verify in security/ops domain)
- [ ] AWS Security Group does NOT expose 5432/6379/9000/9001/20128/8000 publicly
- [ ] `.env` file perms 0600 on host (not 0755)
- [ ] Admin panel IP allowlist enforced at Caddy edge + app
- [ ] `admin_jwt_secret` is a real secret in prod (not `change-me-in-prod`)
- [ ] SPA dev-dep esbuild advisory triaged (dev-only) or bumped

## AWS deploy (to verify read-only via `ssh flashbot`, ops domain)
- [ ] Deployed SHA == merged `origin/main` SHA
- [ ] Containers healthy; images digest-pinned (not `:latest`)
- [ ] `alembic current` == `0042_search_model`
- [ ] Backup job runs + restore drill passes
- [ ] Rollback runbook validated (previous image tag available)

## Rollback readiness
- [ ] Previous good image tag/SHA recorded before deploy
- [ ] DB backup taken immediately pre-migration
- [ ] Documented one-command rollback path
