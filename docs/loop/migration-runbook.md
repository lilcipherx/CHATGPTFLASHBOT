# Migration runbook — 0043 / 0044 (production PostgreSQL)

Pre-merge/deploy verification for the two index-backfill migrations added this loop.
Zero-trust: every claim below is checked against the actual migration files + env.py, not docs.

## What ships
- `0043_users_bot_id_index` — `ix_users_bot_id` on `users(bot_id)`.
- `0044_missing_model_indexes` — `ix_gifts_buyer_id`, `ix_gifts_redeemed_by`,
  `ix_contest_entries_user_id`.
- Both are **additive indexes only** — no column/table/constraint/data changes, no runtime-code
  change. Purely close model↔migration index drift (findings F2/F3).

## Ordering (verified)
- Linear chain, single head: `... 0042_search_model → 0043_users_bot_id_index →
  0044_missing_model_indexes (head)`. Verified `alembic heads` = `0044`.
- Production is expected at `0042` (confirm with `alembic current` on the host during the
  read-only inventory step) → deploy applies exactly 0043 then 0044.

## CONCURRENTLY + transaction mode (verified — this is the critical part)
- `env.py` runs **all migrations inside ONE outer transaction** (`with
  context.begin_transaction(): context.run_migrations()`; no `transaction_per_migration`).
- `CREATE INDEX CONCURRENTLY` **cannot run inside a transaction**. Both migrations wrap the
  Postgres path in `op.get_context().autocommit_block()`, which commits the current tx, runs the
  statement in autocommit, then reopens a tx — the Alembic-sanctioned pattern for CONCURRENTLY.
- This mirrors the already-deployed 0004/0007/0021/0023/0038 index migrations exactly (same
  env.py, same autocommit_block idiom) → the pattern is proven in this stack.
- SQLite/dev path uses a plain `create_index` (no CONCURRENTLY); tests exercise it.
- Idempotent: each index is guarded by `_has_index(...)` so a re-run (or a create_all dev DB)
  is a no-op — safe to re-apply after a partial failure.

### Known caveat to watch on the host
- `CREATE INDEX CONCURRENTLY` is slower and, if interrupted, can leave an **INVALID** index.
  If a build is interrupted: `DROP INDEX CONCURRENTLY IF EXISTS <name>;` then re-run
  `alembic upgrade head` (the `_has_index` guard skips already-built ones).
- Because autocommit_block commits mid-chain, a failure in 0044 after 0043 committed leaves the
  DB at 0043 with 0043's index built — re-running upgrade resumes cleanly (idempotent).

## Backup (mandatory before deploy)
1. Take a fresh dump immediately before migrating (host already has `scripts/backup.sh`):
   `docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm backup` (or the
   host's scheduled `backup` service) → verify the dump file exists and is non-zero.
2. Record the current deployed image tag/SHA and `alembic current` BEFORE deploy (rollback anchor).

## Rollback plan
- **Schema rollback (rarely needed — indexes are additive & non-breaking):**
  `alembic downgrade 0042_search_model` — both migrations implement a symmetric
  `DROP INDEX CONCURRENTLY` (Postgres) / `drop_index` (SQLite) downgrade, guarded by
  `_has_index`. Dropping these indexes only reverts a performance improvement; no data loss.
- **App rollback:** redeploy the previously-recorded image tag/SHA. Since these migrations are
  additive indexes, the OLD app runs fine against the NEW (indexed) schema — so an app rollback
  does NOT require a schema downgrade. Prefer app-only rollback; leave the indexes in place.
- **Restore-from-backup (only if data corruption, not applicable here):** `scripts/restore.sh`
  against the pre-deploy dump; `scripts/restore_test.sh` validates a restore first.

## Deploy gate checklist for these migrations
- [ ] Prod `alembic current` == `0042` (read-only inventory)
- [ ] Fresh backup taken + verified non-zero
- [ ] Deployed image tag/SHA recorded (rollback anchor)
- [ ] `alembic upgrade head` → reaches `0044`; watch for INVALID index on interruption
- [ ] Post-deploy: `\d+ users` / `\d+ gifts` / `\d+ contest_entries` show the 4 new indexes VALID
- [ ] App healthy (`/health/ready`), no error-rate change
