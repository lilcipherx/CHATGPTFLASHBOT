# Restore

> **Destructive.** `scripts/restore.sh` drops and recreates the `public` schema
> before loading the dump. Take a fresh backup first and double-check the target DB.

## Steps
1. Pick a dump (verify integrity is automatic — checksum + gzip test):
   ```bash
   ls -lh /backups/*.sql.gz
   ```
2. (Recommended) Put the app in maintenance / stop writers:
   ```bash
   docker compose stop bot api worker beat
   ```
3. Restore:
   ```bash
   docker compose exec -e FORCE=0 backup /bin/sh -c \
     'POSTGRES_HOST=postgres POSTGRES_USER=$POSTGRES_USER POSTGRES_DB=$POSTGRES_DB \
      POSTGRES_PASSWORD=$POSTGRES_PASSWORD sh /restore.sh /backups/<dump>.sql.gz'
   ```
   (Or run `scripts/restore.sh <dump>` from a shell with `psql` + the env vars.)
   Set `FORCE=1` to skip the confirmation prompt in automation.
4. Confirm the migration head matches the code:
   ```bash
   docker compose exec api alembic current   # should equal `alembic heads`
   ```
   If the dump predates the deployed code, run `alembic upgrade head`.
5. Restart and smoke-test:
   ```bash
   docker compose start bot api worker beat
   BASE_URL=https://$DOMAIN scripts/smoke_test.sh
   ```

## Partial / point-in-time
This project uses logical dumps (RPO ≈ backup interval). For lower RPO, enable
Postgres WAL archiving + base backups (pgBackRest/WAL-G) and follow that tool's
PITR procedure — out of scope for the bundled scripts.

## Dry-run / validation
Always validate an unfamiliar dump first with the non-destructive drill:
```bash
scripts/restore_test.sh /backups/<dump>.sql.gz
```
