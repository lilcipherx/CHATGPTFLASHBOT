#!/bin/sh
# Periodic pg_dump -> /backups with integrity verification, checksums, retention,
# optional S3 upload and optional notification webhook. Runs in the `backup`
# service container (loops on BACKUP_INTERVAL_SECONDS).
#
# Env:
#   BACKUP_INTERVAL_SECONDS (default 86400)   BACKUP_RETENTION_DAYS (default 14)
#   POSTGRES_HOST/USER/DB/PASSWORD            S3_BUCKET + aws creds -> S3 push
#   BACKUP_WEBHOOK_URL                        -> POSTed {status,file,size} per run
set -eu

INTERVAL="${BACKUP_INTERVAL_SECONDS:-86400}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
DB_HOST="${POSTGRES_HOST:-postgres}"
DB_USER="${POSTGRES_USER:-aiobot}"
DB_NAME="${POSTGRES_DB:-aiobot}"
export PGPASSWORD="${POSTGRES_PASSWORD:?required: set POSTGRES_PASSWORD in the environment}"  # FIX: MISC - refuse to run with the default password

log() { echo "[backup $(date -u +%FT%TZ)] $*"; }

notify() {  # notify <status> <file> <size>
  [ -n "${BACKUP_WEBHOOK_URL:-}" ] || return 0
  curl -fsS -m 10 -X POST "${BACKUP_WEBHOOK_URL}" -H 'Content-Type: application/json' \
    -d "{\"status\":\"$1\",\"file\":\"$2\",\"size\":\"$3\"}" >/dev/null 2>&1 || true
}

backup_once() {
  TS="$(date +%Y%m%d-%H%M%S)"
  OUT="/backups/${DB_NAME}-${TS}.sql.gz"
  log "dumping ${DB_NAME} -> ${OUT}"

  if ! pg_dump -h "${DB_HOST}" -U "${DB_USER}" "${DB_NAME}" | gzip > "${OUT}"; then
    log "ERROR: pg_dump failed"; rm -f "${OUT}"; notify failed "${OUT}" 0; return 1
  fi

  # Integrity: the gzip must decompress cleanly, else the dump is useless.
  if ! gzip -t "${OUT}"; then
    log "ERROR: integrity check failed for ${OUT}"; rm -f "${OUT}"; notify failed "${OUT}" 0; return 1
  fi

  sha256sum "${OUT}" > "${OUT}.sha256" 2>/dev/null || shasum -a 256 "${OUT}" > "${OUT}.sha256"
  SIZE="$(wc -c < "${OUT}")"
  log "ok ${OUT} (${SIZE} bytes), checksum written"

  # Optional offsite copy.
  if [ -n "${S3_BUCKET:-}" ] && command -v aws >/dev/null 2>&1; then
    if aws s3 cp "${OUT}" "s3://${S3_BUCKET}/backups/" && \
       aws s3 cp "${OUT}.sha256" "s3://${S3_BUCKET}/backups/"; then
      log "uploaded to s3://${S3_BUCKET}/backups/"
    else
      log "WARN: S3 upload failed"
    fi
  fi

  # Retention (local).
  find /backups -name "${DB_NAME}-*.sql.gz*" -mtime "+${RETENTION_DAYS}" -delete || true
  notify ok "${OUT}" "${SIZE}"
}

# One-shot mode for cron/manual: `backup.sh once`.
if [ "${1:-}" = "once" ]; then backup_once; exit $?; fi

while true; do
  backup_once || log "backup run failed (will retry next interval)"
  sleep "${INTERVAL}"
done
