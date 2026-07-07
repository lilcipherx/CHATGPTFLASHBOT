#!/usr/bin/env bash
# Automated restore drill: spin up a THROWAWAY Postgres, restore the latest dump
# into it, and assert the schema + core tables came back. Proves the backups are
# actually restorable (a backup you've never restored is not a backup).
#
#   scripts/restore_test.sh [path-to-dump.sql.gz]   # default: newest in ./backups
#
# Requires Docker. Exits non-zero if the restore or verification fails — wire it
# into a weekly CI/cron job.
set -euo pipefail

DUMP="${1:-$(ls -t backups/*.sql.gz 2>/dev/null | head -1 || true)}"
[ -n "${DUMP}" ] && [ -f "${DUMP}" ] || { echo "no dump found (pass one explicitly)"; exit 1; }

CONTAINER="aibot-restore-test-$$"
PORT=55432
echo "[restore-test] starting throwaway Postgres ($CONTAINER)..."
docker run -d --rm --name "$CONTAINER" \
  -e POSTGRES_PASSWORD=test -e POSTGRES_USER=test -e POSTGRES_DB=test \
  -p ${PORT}:5432 postgres:16-alpine >/dev/null

cleanup() { docker stop "$CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "[restore-test] waiting for readiness..."
for _ in $(seq 1 30); do
  if docker exec "$CONTAINER" pg_isready -U test >/dev/null 2>&1; then break; fi
  sleep 1
done

echo "[restore-test] restoring ${DUMP}..."
gunzip -c "${DUMP}" | docker exec -i "$CONTAINER" psql -U test -d test -v ON_ERROR_STOP=1 >/dev/null

echo "[restore-test] verifying tables..."
TABLES=$(docker exec "$CONTAINER" psql -U test -d test -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")
USERS=$(docker exec "$CONTAINER" psql -U test -d test -tAc \
  "SELECT count(*) FROM users;" 2>/dev/null || echo "MISSING")

echo "[restore-test] public tables: ${TABLES}, users rows: ${USERS}"
if [ "${TABLES:-0}" -lt 10 ] || [ "${USERS}" = "MISSING" ]; then
  echo "[restore-test] FAILED — restored schema looks incomplete"; exit 1
fi
echo "[restore-test] PASS — backup is restorable."
