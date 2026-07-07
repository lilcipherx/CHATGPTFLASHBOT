# Backup

The `backup` service (`scripts/backup.sh`) runs in the prod stack and performs
verified, checksummed `pg_dump` backups on a schedule.

## What it does
- `pg_dump | gzip` → `/backups/<db>-<ts>.sql.gz` (a Docker volume).
- **Integrity**: `gzip -t` verifies each dump; a corrupt dump is discarded.
- **Checksum**: writes `<dump>.sha256` alongside.
- **Retention**: deletes dumps older than `BACKUP_RETENTION_DAYS` (default 14).
- **Offsite** (optional): if `S3_BUCKET` is set and `aws` is available, uploads
  the dump + checksum to `s3://$S3_BUCKET/backups/`.
- **Notify** (optional): POSTs `{status,file,size}` to `BACKUP_WEBHOOK_URL`.

## Config
`BACKUP_INTERVAL_SECONDS` (86400), `BACKUP_RETENTION_DAYS` (14),
`POSTGRES_HOST/USER/DB/PASSWORD`, `S3_BUCKET`, `BACKUP_WEBHOOK_URL`.

## Manual / one-shot
```bash
docker compose exec backup /bin/sh /backup.sh once
ls -lh $(docker volume inspect -f '{{.Mountpoint}}' <project>_backups)
```

## Verify a backup is restorable (do this regularly!)
```bash
scripts/restore_test.sh                 # newest dump in ./backups
scripts/restore_test.sh path/to/dump.sql.gz
```
This spins a throwaway Postgres, restores the dump, and asserts the schema +
`users` table came back. Wire it into a weekly cron/CI job — *a backup you have
never restored is not a backup*.

## Restoring for real
See [RESTORE.md](RESTORE.md).

## Recommended policy
- Daily automated dumps, 14-day local retention, offsite (S3) copy.
- Weekly automated restore drill (`restore_test.sh`).
- Before every prod migration: take a one-shot backup.
- RPO ≈ 24h with daily dumps; tighten with WAL archiving / PITR if needed.
