# Loop Engineering — AWS inventory

Independently verified **read-only** via `ssh flashbot` on 2026-07-13. No changes were made to
the server. AWS receives ONLY the exact merged `origin/main` SHA (never server-only edits).

## Access / host
- `flashbot` → HostName `18.198.8.92`, User `ubuntu`. Host `ip-172-31-45-10`, Ubuntu 24.04,
  kernel 6.17.0-1019-aws. Disk `/` 65% used (19G/29G).

## Deploy layout (verified)
- **Directory-swap, NOT a git checkout.** Current: `/home/ubuntu/CHATGPTFLASHBOT` (`.git` absent).
  Rollback dirs kept: `CHATGPTFLASHBOT.predeploy.20260712-121634` (last deploy = 2026-07-12) and
  `CHATGPTFLASHBOT.old.20260707-053733`.
- App images built on host (`chatgptflashbot-api/bot/worker/beat` — no registry tag), not pulled
  from GHCR. Deploy = swap dir + build + recreate.

## Schema state (verified) — gates the migration deploy
- `alembic_version.version_num = 0042_search_model`. So deploying this branch applies exactly
  **0043 then 0044** (the two index backfills). Matches `docs/loop/migration-runbook.md`.

## Containers (docker ps) — all Up, core services healthy
caddy `caddy:2-alpine` · postgres `postgres:16-alpine` (healthy) · redis `redis:7-alpine`
(healthy) · api (healthy) · omniroute `:latest` (healthy) · minio `minio/minio:latest` · backup ·
bot · worker · beat · pgbouncer `edoburu/pgbouncer:latest` (Up 5 days).

## Network exposure (verified — old audit P0 NOT reproduced)
- Only `0.0.0.0:22`, `0.0.0.0:80`, `0.0.0.0:443` are publicly bound. API is `127.0.0.1:8000`.
- **No 5432 / 6379 / 9000 / 9001 / 20128 bound to 0.0.0.0** — postgres/redis/minio/omniroute are
  docker-network-internal only. The prod compose `ports: !reset []` / `!override 127.0.0.1:...`
  hardening is effective on the live host. The older "internal ports exposed on 0.0.0.0" P0 is
  NOT present now.
- `ufw` is **inactive** — perimeter is the AWS Security Group. Defense-in-depth: enabling ufw
  (allow 22/80/443) would add a second layer, but is lower priority since nothing internal is
  0.0.0.0-bound. (Host-only change — owner's call; not a repo edit.)

## Security posture confirmations (empirical, against real prod env)
- `api` container env: `ENV=prod`, `WEBHOOK_BASE_URL` set, `PUBLIC_DEPLOY` empty →
  `is_public_deploy = True`. Therefore `_require_prod_secret()` boot guards are ACTIVE and the
  Mini App dev-bypass is fail-closed. **This empirically confirms Loop L2 findings C1 and C3**
  (safe) against the actual deployment, not just the code.

## Backups (verified)
- Backup container logs: `2026-07-12T07:22:25Z ok /backups/aiobot-20260712-072225.sql.gz
  (12225 bytes), checksum written`. DB name `aiobot`. Checksummed gzip dumps are produced on a
  schedule; latest ~1 day old. (Restore drill `scripts/restore_test.sh` not exercised this loop.)

## Image-pinning drift (minor)
- Live `docker-compose.prod.yml` pins all images by `@sha256` (grep found no unpinned `image:`).
  But several long-running containers still show mutable tags (`pgbouncer:latest` Up 5d,
  `minio/minio:latest`, `omniroute:latest`) — they predate the pinned compose and weren't
  recreated. A `--force-recreate` on the next deploy aligns them to the pinned digests. P3.

## Deployed SHA
- Host is not a git repo, so no SHA on disk. Deployed code == contents of the last-swapped dir
  (predeploy marker 2026-07-12). After this loop's merge, deploy target == merged `origin/main`.

## Rollback evidence
- `.predeploy.*` / `.old.*` directory snapshots provide app rollback; DB rollback via the
  checksummed `aiobot-*.sql.gz` dumps (`scripts/restore.sh`). See migration-runbook for the
  additive-index rollback (app-only rollback suffices; indexes are non-breaking).
