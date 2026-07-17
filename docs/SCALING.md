# Scaling to millions of users

> Database & throughput strategy. What is already in place, what to add, and in what
> order. Grounded in the current schema and deployment topology.

## Already in place (the foundation — don't regress)

- **Composite indexes on the hot paths.**
  - `generation_jobs (user_id, service, created_at)` — Mini App History / refund queries.
  - `generation_jobs (status, created_at)` — the stuck-job sweep.
  - `transactions (status, created_at)` — the §8 revenue/DAU dashboards + status lookups.
- **Batched retention** (`workers/retention_extra_tasks.py`, `prune_results`): audit logs
  > 365d, transactions > 7y, support > 1y, generation/gallery artifacts (90/180d) —
  each bounded to 50k rows/run to avoid long transactions.
- **Connection pooling**: PgBouncer (transaction pooling) wired in the prod compose;
  the app drops its own pool + disables prepared-statement caches when
  `DB_PGBOUNCER=true` (see `core/db.py`).
- **No mass writes on the hot path**: weekly quota resets lazily per user on next
  request — no full-table `UPDATE users`.
- **Read-replica scaffolding**: `get_read_session` / `ReadSessionFactory` route to a
  replica when `DATABASE_READ_URL` is set, else the primary (a no-op until provisioned).

## Gaps to close for true millions-scale (prioritized)

### P1 — Partition `generation_jobs` by `created_at` (monthly range partitions)
The fastest-growing table (one row per generation). At millions of users the batched
retention `DELETE` can't keep up and causes bloat + autovacuum pressure. Range
partitions make retention a `DETACH`/`DROP PARTITION` — **O(1)** instead of a scanning
delete — and hot queries prune to recent partitions. Indexes are inherited per
partition. *Cost: a migration (create partitioned table, migrate data, swap) + a
retention-cron change to drop partitions.*

### P1 — Enable PgBouncer in prod
The compose ships it commented. Set `DB_PGBOUNCER=true` and point the DSN at
`pgbouncer:6432`. Without it, `gunicorn -w4` + the bot + N ARQ workers + beat each
open `(pool_size + max_overflow)` connections → they exhaust Postgres `max_connections`.
*Cost: env + compose config.*

### P2 — Read replica + read/write split
All reads and writes hit one primary. Route lag-tolerant, read-heavy traffic to a
replica via `get_read_session`:
- **Good candidates** (read-only, staleness OK): analytics/§8 dashboards, catalogs
  (`/categories`, effect lists), Mini App History (`/jobs`) if a few seconds of lag is
  acceptable.
- **Keep on the primary** (read-your-write / money): `/profile` right after a purchase,
  checkout, refunds, anything that reads a value it just wrote.
Wire endpoints incrementally: change `Depends(get_session)` → `Depends(get_read_session)`
only where correctness tolerates replication lag. *Cost: per-endpoint change + a replica.*

### P2 — Move analytics off the OLTP primary
The §8 dashboards scan `transactions (status, created_at)`; at scale these analytical
scans compete with money-path OLTP. Either serve them from the replica (P2 above) or
maintain rollup tables / a materialized view refreshed by a cron.

### P3 — Partition `transactions` (7y) and `admin_audit_log`
Same technique as generation_jobs, lower urgency (smaller volume, rarer retention).

## Suggested order
1. **PgBouncer on** — quick, biggest immediate win on connection limits.
2. **Partition `generation_jobs`** — removes the primary bloat/retention risk.
3. **Read replica + split** — offloads read traffic (History, analytics, catalogs).
4. **Analytics → replica/rollups**, then **partition transactions/audit**.

## Verify capacity before launch
Local load tests (in-process or uvicorn + SQLite) only measure application-layer
efficiency. **True capacity requires staging on Postgres + Redis with the prod topology**
(`gunicorn -w4` + PgBouncer + replica). Run `loadtests/k6` / `loadtests/locust` against
staging and watch p95 under `soak` for connection-pool exhaustion.

Current app-layer profiling (in-process harness, SQLite + fakeredis) after the
read-path work: every hot Mini App read endpoint is healthy — `/profile` p99 ~0.6s
@100 concurrent (was ~8.4s before the sections cache), `/jobs` `/billing/offers`
`/effects` `/categories` all 350–1800 rps with p99 < 0.6s. **No code-level hotspot
remains on the read paths** — further gains now come from the infra below, not code.

---

# Runbook — execute on STAGING first (Postgres/Docker required; not locally verifiable)

> These steps need a real Postgres + Docker + a replica, which the dev box doesn't
> have. Apply on staging, run the load tests, and confirm before prod.

## R1 — Enable PgBouncer (quickest win)
The compose already ships a (commented) `pgbouncer` service and the app already
handles transaction pooling when `db_pgbouncer=true` (see `core/db.py`).

1. Uncomment the `pgbouncer` service in `docker-compose.prod.yml`.
2. Point the app at it and turn on txn-pooling mode (`.env`):
   ```
   DATABASE_URL=postgresql+asyncpg://$POSTGRES_USER:$POSTGRES_PASSWORD@pgbouncer:6432/$POSTGRES_DB
   DB_PGBOUNCER=true
   ```
   The app then uses `NullPool` + disables prepared-statement caches (required under
   transaction pooling) — already wired in `core/db.py`.
3. Verify: `SHOW POOLS;` on pgbouncer (`psql -p 6432 pgbouncer`); app connection count
   to Postgres should collapse to `DEFAULT_POOL_SIZE`. Re-run loadtests, watch that
   `pool_timeout` errors disappear under concurrency.

## R2 — Provision a read replica + wire endpoints
Scaffolding is already in place: `get_read_session` / `ReadSessionFactory` +
`DATABASE_READ_URL` fall back to the primary when unset. The catalog endpoints
(`/photo-effects`, `/video-effects`, `/effects`) already use it.

1. Stand up a streaming replica; set `DATABASE_READ_URL` to its DSN.
2. Verify catalog endpoints still return 200 and now hit the replica (check replica
   `pg_stat_activity`).
3. Wire more **lag-tolerant, write-free** endpoints incrementally: `Depends(get_session)`
   → `Depends(get_read_session)`. Candidates: the §8 analytics/dashboard reads. Guard
   each with the read-only test pattern (`tests/test_catalog_read_session.py` pins
   `PRAGMA query_only=ON` so any accidental write fails the test).
   **Do NOT** move read-your-write paths (`/profile` right after purchase, `/jobs`
   polling a just-submitted job, checkout, refunds).

## R3 — Partition `generation_jobs` by month (biggest bloat risk) — a real project, not a one-line migration
Postgres range-partitioning by `created_at` turns retention into an O(1)
`DETACH`/`DROP PARTITION` instead of the batched `DELETE`, and prunes hot queries to
recent partitions.

**Caveat that makes this a project, not a quick migration:** Postgres requires the
partition key (`created_at`) to be part of the primary key / every UNIQUE constraint.
`generation_jobs` currently has PK `job_id` (UUID). Partitioning therefore needs:
- PK → `(job_id, created_at)` (a model change), and
- every `session.get(GenerationJob, job_id)` call site updated to carry `created_at`
  (or switched to a `select().where(job_id == …)` that reads a recent-partition slice).

Approach on staging:
1. Change the model PK to `(job_id, created_at)`; grep + fix the `session.get(...)`
   call sites (worker claim/finalise, refund, sweep, `/api/jobs/{id}`).
2. Migration (Postgres-only; **no-op on SQLite** so tests/CI stay green — guard with
   `if op.get_bind().dialect.name == "postgresql"`):
   - create `generation_jobs_new` `PARTITION BY RANGE (created_at)` with the composite PK;
   - create monthly partitions (or use `pg_partman` for auto-creation + retention);
   - copy rows (trivial pre-launch — the table is ~empty), swap names, drop the old.
3. Change the retention cron (`workers/retention_extra_tasks.py`) from batched `DELETE`
   to `DETACH PARTITION` + `DROP` of partitions older than the window.
4. Load-test + verify partition pruning (`EXPLAIN` shows only recent partitions scanned).

## R4 — Analytics off OLTP, then partition `transactions` / `admin_audit_log`
Serve the §8 dashboards from the replica (R2) or from rollup tables refreshed by a
cron; then apply the R3 technique to `transactions` (7-year retention) and the audit
log (lower urgency, smaller volume).
