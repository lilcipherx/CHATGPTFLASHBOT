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
