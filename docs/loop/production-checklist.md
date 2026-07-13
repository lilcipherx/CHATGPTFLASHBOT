# Loop Engineering — production checklist

Go/no-go gates for staging + production. A box is checked ONLY with verified evidence
(command output / commit SHA / screenshot). Zero-trust: no box is checked from a doc claim.

## Local quality gates (verified @ bb44014, Loop 0)
- [x] `ruff check .` — PASS
- [x] `pytest -q` — 905 passed / 0 failed
- [x] coverage `--fail-under=67` — PASS. **Global 70.36%** (10059/14296); **critical-domain 85.2%**
      (2616/3070) after the coverage push. Suite 1014 passed.
- [x] `bandit -r core api bot workers -ll -q` — exit 0
- [ ] `pip-audit -r requirements.txt` — BLOCKED locally (venv module missing); rely on CI
- [x] `alembic upgrade head` + `check_migrations` — PASS, no drift, single head 0042
- [x] miniapp: vitest 17 / tsc clean / build / e2e 4 passed
- [x] admin: vitest 26 / tsc clean / build
- [ ] `docker compose build` — not yet run locally (ops domain)
- [ ] mypy — 306 errors (non-blocking); tracked as debt

## CI / GitHub (finding F1 — see ci-remediation.md)
- [ ] **BLOCKER (owner): GitHub Actions restored** — currently 0-jobs startup_failure (billing/
      minutes on a private repo). Fix: restore Actions billing / make repo public / self-hosted runner.
- [x] Compensating control: `scripts/ci_local.sh` mirrors the ci.yml gate set locally (this loop ran all green)
- [ ] Branch protection on `main` requires CI checks — UNAVAILABLE on the current plan (private + free)
- [ ] Release workflow builds+pushes GHCR image on tag (untested — Actions down)

## Security posture (verified read-only via ssh flashbot)
- [x] Internal ports NOT publicly bound — only 22/80/443 on 0.0.0.0; api on 127.0.0.1:8000;
      no 5432/6379/9000/9001/20128 exposed (old P0 not reproduced)
- [x] `is_public_deploy = True` on prod (WEBHOOK_BASE_URL set) → boot guards active → `admin_jwt_secret`
      is real (api wouldn't boot on the default) and admin IP allowlist is enforced at boot
- [ ] `ufw` inactive (perimeter = AWS SG) — optional defense-in-depth (host-only, owner's call)
- [ ] `.env` file perms 0600 on host — not re-checked this loop
- [x] SPA dev-dep esbuild advisory triaged: dev-only (vite/vitest), prod build unaffected — accept (P3)

## AWS deploy (verified read-only via `ssh flashbot`)
- [ ] Deployed SHA == merged `origin/main` — pending (deploy after merge)
- [x] Containers healthy (postgres/redis/api/omniroute healthy; all Up)
- [~] Images: live compose digest-pinned, but pgbouncer/minio/omniroute containers still on `:latest`
      (predate pinned compose) — align on next `--force-recreate` deploy (P3)
- [x] `alembic current` == `0042_search_model` (so deploy applies exactly 0043 + 0044)
- [x] Backup job runs + checksummed dumps (`aiobot-*.sql.gz`); restore DRILL not exercised this loop
- [x] Rollback anchors present: `.predeploy.*` / `.old.*` dir snapshots + backup dumps (see migration-runbook.md)

## Rollback readiness
- [ ] Previous good image tag/SHA recorded before deploy
- [ ] DB backup taken immediately pre-migration
- [ ] Documented one-command rollback path
