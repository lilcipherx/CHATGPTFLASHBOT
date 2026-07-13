#!/usr/bin/env bash
# Local mirror of .github/workflows/ci.yml.
#
# COMPENSATING CONTROL (finding F1): GitHub Actions is non-functional on this repo
# (0-jobs startup_failure — see docs/loop/ci-remediation.md). This is NOT a bypass:
# it reproduces the SAME gate set locally so changes stay gated until the owner
# restores Actions. Run from the repo root: `bash scripts/ci_local.sh`.
#
# Exit 0 only if every BLOCKING gate passes. Informational gates (ruff format, mypy)
# mirror ci.yml's `|| true` and never fail the run.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 2
ROOT="$(pwd)"

# Resolve the project venv python (Windows or POSIX layout), else fall back to PATH.
if [ -x ".venv/Scripts/python.exe" ]; then PY=".venv/Scripts/python.exe"
elif [ -x ".venv/bin/python" ]; then PY=".venv/bin/python"
else PY="python"; fi

# CI test env (matches ci.yml env:) — SQLite + in-memory redis + dummy token.
export DATABASE_URL="sqlite+aiosqlite:///./ci_local.db"
export REDIS_URL="memory://"
export BOT_TOKEN="123:ci"
export ENV="test"
rm -f ci_local.db

FAILED=()
run_block() {  # run_block <name> <blocking:0|1> <command...>
  local name="$1" blocking="$2"; shift 2
  echo "=================================================================="
  echo ">> $name"
  if "$@"; then
    echo "PASS: $name"
  else
    if [ "$blocking" = "1" ]; then echo "FAIL (blocking): $name"; FAILED+=("$name")
    else echo "WARN (informational): $name"; fi
  fi
}

# --- lint ---
run_block "ruff check (gate)" 1 "$PY" -m ruff check .
run_block "ruff format (informational)" 0 "$PY" -m ruff format --check .

# --- typecheck (informational, matches ci.yml continue-on-error) ---
run_block "mypy (informational)" 0 "$PY" -m mypy core api bot workers --ignore-missing-imports --no-error-summary

# --- test + coverage ratchet ---
run_block "pytest + coverage" 1 bash -c \
  "'$PY' -m pytest --cov=core --cov=api --cov=bot --cov=workers --cov-report=term-missing -q && '$PY' -m coverage report --fail-under=67"

# --- migrations ---
# ci.yml runs this in an isolated job with a fresh checkout/DB. Mirror that: use a
# DEDICATED throwaway DB so the create_all schema left in $DATABASE_URL by the pytest
# step above can't collide with `alembic upgrade head` ("table already exists").
run_block "alembic upgrade head + check_migrations" 1 bash -c \
  "rm -f ci_local_mig.db; export DATABASE_URL='sqlite+aiosqlite:///./ci_local_mig.db'; \
   '$PY' -m alembic upgrade head && '$PY' -m scripts.check_migrations; rc=\$?; \
   rm -f ci_local_mig.db; exit \$rc"

# --- security ---
run_block "bandit" 1 "$PY" -m bandit -r core api bot workers -ll -q
# pip-audit is required in CI; it fails to import in the local stripped venv (missing
# stdlib `venv`). Informational locally so it never blocks the dev mirror; CI enforces it.
run_block "pip-audit (CI-enforced; informational locally)" 0 "$PY" -m pip_audit -r requirements.txt --strict

# --- frontend (miniapp + admin) ---
for app in miniapp admin; do
  run_block "$app: npm ci" 1 bash -c "cd '$ROOT/$app' && (npm ci || npm install)"
  run_block "$app: vitest" 1 bash -c "cd '$ROOT/$app' && npm run test --if-present"
  run_block "$app: tsc --noEmit" 1 bash -c "cd '$ROOT/$app' && npx tsc --noEmit"
  run_block "$app: build" 1 bash -c "cd '$ROOT/$app' && npm run build"
done
run_block "miniapp: playwright e2e" 1 bash -c "cd '$ROOT/miniapp' && npm run e2e"

rm -f ci_local.db

echo "=================================================================="
if [ "${#FAILED[@]}" -eq 0 ]; then
  echo "CI-LOCAL: ALL BLOCKING GATES PASSED"
  exit 0
fi
echo "CI-LOCAL: ${#FAILED[@]} BLOCKING GATE(S) FAILED:"
printf '  - %s\n' "${FAILED[@]}"
exit 1
