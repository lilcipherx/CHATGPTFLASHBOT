-- PostgreSQL maintenance + diagnostics for ИИ Бот №1 (run on prod with psql).
-- Most of this is observational; the VACUUM/ANALYZE/REINDEX are the only writes.

-- 1) Reclaim bloat + refresh planner stats (safe; ANALYZE is cheap, VACUUM online).
VACUUM (ANALYZE);

-- 2) Largest tables (where bloat/IO concentrates).
SELECT relname AS table,
       pg_size_pretty(pg_total_relation_size(relid)) AS total,
       pg_size_pretty(pg_relation_size(relid))       AS heap,
       n_live_tup AS live_rows, n_dead_tup AS dead_rows
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 20;

-- 3) UNUSED indexes (idx_scan = 0): candidates to drop (write cost, no reads).
SELECT schemaname, relname AS table, indexrelname AS index,
       pg_size_pretty(pg_relation_size(indexrelid)) AS size, idx_scan AS scans
FROM pg_stat_user_indexes
WHERE idx_scan = 0
ORDER BY pg_relation_size(indexrelid) DESC;

-- 4) Tables with the most sequential scans (missing-index candidates).
SELECT relname AS table, seq_scan, idx_scan,
       seq_tup_read, n_live_tup AS rows
FROM pg_stat_user_tables
WHERE seq_scan > 0
ORDER BY seq_scan DESC
LIMIT 20;

-- 5) Slowest statements (requires the pg_stat_statements extension).
-- CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
SELECT calls, round(total_exec_time::numeric, 1) AS total_ms,
       round(mean_exec_time::numeric, 2) AS mean_ms, left(query, 120) AS query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;

-- 6) Verify the hot-path indexes this app relies on actually exist.
SELECT indexname FROM pg_indexes
WHERE indexname IN (
  'ix_genjobs_user_service_created', 'ix_genjobs_status_created',
  'ix_users_username_trgm', 'ix_users_phone_trgm', 'ix_users_is_banned'
)
ORDER BY indexname;

-- 7) Sanity check the planner uses an index for admin user search (no seq scan).
-- EXPLAIN ANALYZE SELECT * FROM users WHERE username ILIKE '%john%' LIMIT 50;

-- 8) Rebuild indexes if bloated (CONCURRENTLY avoids locking; run per-index in prod).
-- REINDEX INDEX CONCURRENTLY ix_genjobs_status_created;
