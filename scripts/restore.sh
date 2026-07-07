#!/bin/sh
# Restore a pg_dump .sql.gz into the target database. DESTRUCTIVE: it drops and
# recreates the public schema, so guard it behind an explicit confirmation.
#
#   scripts/restore.sh /backups/aiobot-20260620-030000.sql.gz
#
# Env: POSTGRES_HOST/USER/DB/PASSWORD. Set FORCE=1 to skip the prompt (automation).
set -eu

DUMP="${1:?usage: restore.sh <dump.sql.gz>}"
DB_HOST="${POSTGRES_HOST:-postgres}"
DB_USER="${POSTGRES_USER:-aiobot}"
DB_NAME="${POSTGRES_DB:-aiobot}"
export PGPASSWORD="${POSTGRES_PASSWORD:?required: set POSTGRES_PASSWORD in the environment}"  # FIX: MISC - refuse to run with the default password

[ -f "${DUMP}" ] || { echo "no such file: ${DUMP}" >&2; exit 1; }

# Verify checksum + gzip integrity before touching the DB.
if [ -f "${DUMP}.sha256" ]; then
  echo "[restore] verifying checksum..."
  (cd "$(dirname "${DUMP}")" && (sha256sum -c "$(basename "${DUMP}").sha256" \
     || shasum -a 256 -c "$(basename "${DUMP}").sha256")) || {
       echo "[restore] checksum MISMATCH — aborting" >&2; exit 1; }
fi
gzip -t "${DUMP}" || { echo "[restore] corrupt gzip — aborting" >&2; exit 1; }

if [ "${FORCE:-0}" != "1" ]; then
  printf "This will WIPE and restore '%s' from %s. Type 'yes' to continue: " "${DB_NAME}" "${DUMP}"
  read -r ans
  [ "${ans}" = "yes" ] || { echo "aborted"; exit 1; }
fi

echo "[restore] resetting schema on ${DB_NAME}@${DB_HOST}..."
psql -h "${DB_HOST}" -U "${DB_USER}" -d "${DB_NAME}" -v ON_ERROR_STOP=1 \
  -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

echo "[restore] loading dump..."
gunzip -c "${DUMP}" | psql -h "${DB_HOST}" -U "${DB_USER}" -d "${DB_NAME}" -v ON_ERROR_STOP=1

echo "[restore] done. Run 'alembic current' to confirm the migration head."
