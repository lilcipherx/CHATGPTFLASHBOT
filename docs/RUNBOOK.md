# Operations runbook

On-call procedures for the live service. Pair with [MONITORING.md](MONITORING.md)
and [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Severity
- **SEV1** — bot/API down, payments broken, data loss. Page immediately.
- **SEV2** — degraded (generation backlog, one provider down, elevated errors).
- **SEV3** — cosmetic / single-user.

## Alert → action

### ApiDown (SEV1)
1. `docker compose ps`; `docker compose logs --tail=200 api`.
2. `curl -s localhost:8000/health` inside the network; check Caddy.
3. Dependency? `curl /health/ready`. If DB/Redis down, recover those first.
4. Restart: `docker compose restart api`. If crash-looping, roll back image tag.

### PostgresDown / RedisDown (SEV1)
1. `docker compose logs postgres` / `redis`. Disk full? `df -h`.
2. Restart the service; verify `/health/ready` 200.
3. If Postgres is corrupt/lost → [RESTORE.md](RESTORE.md) from the latest backup.

### GenerationBacklog (SEV2)
1. `/health/providers` + admin AI-routing health — provider in cooldown/disabled?
2. Scale workers: `docker compose up -d --scale worker=4`.
3. Stuck jobs auto-refund after `STUCK_JOB_MINUTES` via `sweep_stuck_jobs`.

### JobFailuresSpiking (SEV2)
1. Check provider keys/quota/balance; `reset` a tripped account in admin.
2. Inspect `ai.*` / worker logs for the upstream error.

### Payment issues (SEV1)
1. Gateway dashboard → recent webhook deliveries (retries?).
2. Logs: `payment.webhook_rejected` (signature/IP) vs `payment.webhook_retryable`
   (transient — gateway will retry).
3. Manual refund if needed: admin → Payments → Refund (two-phase, retryable).

## Routine ops
- **Deploy:** [DEPLOYMENT.md](DEPLOYMENT.md) §Upgrades; always `smoke_test.sh` after.
- **Backups:** verify the `backup` container is healthy; run a weekly
  `scripts/restore_test.sh` drill.
- **Migrations:** back up first; `check_migrations` in CI; `alembic upgrade head`.
- **Secret rotation:** rotate `ADMIN_JWT_SECRET` (invalidates admin sessions) and
  payment secrets in `.env`; restart. Rotating `ENC_SECRET` requires re-entering
  stored AI keys in admin.
- **Ban/abuse:** admin → Users → ban (enforced globally by ban middleware).
- **Kill a provider:** admin → Providers kill-switch, or disable the AI account.

## Escalation
Capture: alert name, `docker compose ps`, last 200 log lines, `/health/ready` +
`/health/providers` output, recent deploys. Then notify the maintainer
(`SUPPORT_CONTACT`).
