# Monitoring & observability

## Stack
```bash
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d
```
- **Prometheus** scrapes `api:8000/metrics` + postgres/redis exporters.
- **Alertmanager** routes alerts (Telegram receiver — set `ALERT_BOT_TOKEN` + chat id).
- **Grafana** (`:3000`, firewall it) — provisioned datasources + the *ИИ Бот №1
  Overview* dashboard (users, premium, banned, pending/failed jobs, error logs).
- **Loki + Promtail** ship structured (structlog JSON) container logs, 7-day retention.

## App metrics (`/metrics`)
`aibot_users_total`, `aibot_users_premium`, `aibot_users_banned`,
`aibot_jobs_pending`, `aibot_jobs_failed`. Gate with `METRICS_TOKEN` if reachable
(Prometheus: add `params: { token: [...] }`). Caddy 403s `/metrics` on the public host.

## Health probes
- `GET /health` — liveness (no deps).
- `GET /health/ready` — DB + Redis reachable → 200, else 503 (use for orchestrator).
- `GET /health/providers` — which AI/payment backends are configured/available (no secrets).

## Alerts (`monitoring/alerts.yml`)
| Alert | Condition | Severity |
|-------|-----------|----------|
| ApiDown | `up{job=aibot-api}==0` 2m | critical |
| PostgresDown / RedisDown | exporter `up==0` 2m | critical |
| GenerationBacklog | `aibot_jobs_pending>100` 10m | warning |
| JobFailuresSpiking | `increase(aibot_jobs_failed[15m])>20` | warning |
| RedisHighMemory | used/max > 0.9 | warning |
| PostgresConnectionsHigh | `>150` 5m | warning |

## Error tracking
Set `SENTRY_DSN` — bot and api initialise Sentry (10% traces). Add an
Alertmanager/Sentry → Telegram or Slack route for paging.

## What to watch first
1. `ApiDown` / readiness flapping → check DB/Redis.
2. `GenerationBacklog` → scale `worker` replicas or check provider health
   (`/health/providers`, admin AI-routing health view).
3. `JobFailuresSpiking` → AI keys/quota; accounts may be in cooldown.
