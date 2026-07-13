# CI remediation — finding F1 (GitHub Actions non-functional)

## Root cause (verified, zero-trust, not a guess)
GitHub Actions produces **0 jobs / `startup_failure`** for every run on this repo, so no CI gate
actually executes. Evidence gathered via `gh` at bb44014:
- `gh api .../actions/runs/<id>/jobs` → `total_count = 0` for the failing runs (no job ever
  spawns — including PR #3's `pull_request` run, id 29213580822).
- All three workflows report `state = active` (CI, Release, **Dependabot Updates**).
- The failure hits **every** workflow identically — including Dependabot's internally-generated
  version-update workflow, which does NOT use `ci.yml`. A YAML/schema bug in `ci.yml` could only
  break `ci.yml`, not Dependabot. A shared, all-workflow, 0-job failure is the signature of
  **Actions being blocked at the account/repo level** — exhausted free minutes or a spending
  limit on a **private** repo (`.private = true`; branch protection returns HTTP 403
  "Upgrade to GitHub Pro or make this repository public").
- `ci.yml` and `release.yml` YAML both parse and are schema-valid (jobs, `runs-on`, SHA-pinned
  `uses`, valid `needs`). So the workflow files are NOT the cause.

**Conclusion:** this is an account/billing/plan condition, not a code defect. It cannot be fixed
by editing the repo — only the repository owner can restore Actions.

## Owner remediation (pick one — required to restore the real CI gate)
1. **Restore Actions minutes / raise the spending limit** for the account
   (Settings → Billing → Actions; set a spending limit > $0 or top up included minutes). Private
   repos consume paid minutes once the free allotment is exhausted.
2. **Make the repository public** — free unlimited Actions minutes AND enables branch protection
   (required-status-checks) so merges to `main` are genuinely CI-gated. Only do this if the code
   may be public (no secrets are committed — verified: only `.env.example` templates are tracked).
3. **Self-hosted runner** — register a runner (e.g., on the AWS host or a cheap VM) and change
   `runs-on: ubuntu-latest` → `runs-on: self-hosted`. Avoids GitHub-hosted minutes entirely.

After remediation, verify: push a trivial commit to a `fix/**` branch (matches the `ci.yml` push
filter) or open a PR to `main`, then `gh run list` should show the run reaching jobs
(`in_progress` → `success`), not `startup_failure`.

## Compensating control (in place now — does NOT bypass CI)
Until the owner restores Actions, `scripts/ci_local.sh` runs the **same gate set** as `ci.yml`
locally, so changes are still gated. This loop already ran every gate green (see loop-log.md):
ruff, pytest 908, coverage 68% (ratchet 67), bandit, alembic+check_migrations, miniapp/admin
vitest+tsc+build, miniapp Playwright e2e. Only `pip-audit` (blocked in this venv — missing stdlib
`venv` module) and `docker build` require a proper environment / CI to run.

## Secondary workflow note (not the cause, low priority)
`ci.yml`'s push filter is `[main, feat/**, chore/**, fix/**]` — pushes to other branch prefixes
(e.g. `claude/**`) don't trigger CI on push. PRs to `main` still trigger it via `pull_request`.
No change made this loop (would be churn on a workflow that can't run anyway); revisit after
Actions is restored if broader push coverage is wanted.
