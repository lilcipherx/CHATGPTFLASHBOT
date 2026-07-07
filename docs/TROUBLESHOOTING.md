# Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| App won't start: `ADMIN_JWT_SECRET is still the default` | public webhook deploy with default secret | set strong `ADMIN_JWT_SECRET` + `ENC_SECRET` (see [ENV.md](ENV.md)) |
| Mini App shows nothing / every `/api/*` returns 401 | `BOT_TOKEN` empty/wrong → initData HMAC fails | run api with the **real** `BOT_TOKEN`; check device clock (replay window) |
| Mini App 401 in a plain browser (dev) | no Telegram initData | set `DEV_WEBAPP_BYPASS=true` (dev/test only) |
| `/health/ready` returns 503 | DB or Redis down | check `postgres`/`redis` containers; `docker compose logs` |
| Payments not activating | webhook not reaching api / signature / IP | check gateway dashboard deliveries; YooKassa source IP allow-list; `WEBHOOK_BASE_URL`; logs `payment.webhook_*` |
| Real payment occasionally lost | transient webhook verify error returned 200 | already fixed — verify returns 503 on transient (gateway retries); check `payment.webhook_retryable` logs |
| Generations stuck `pending` | Redis/queue down or no worker | check `worker` replicas + Redis; the `sweep_stuck_jobs` cron refunds after `STUCK_JOB_MINUTES` |
| "queue unavailable" 503 on generate | Redis unreachable from api | bring Redis up; the charge is auto-refunded |
| AI replies are errors / `ai.unavailable` | no funded key / all accounts in cooldown | check `/health/providers` + admin AI-routing health; add/fund an account or `reset` it |
| Admin panel 403 | IP not allow-listed | add your IP to `ADMIN_ALLOW_IP` (Caddy) / `ADMIN_IP_ALLOWLIST` |
| `alembic upgrade` fails on fresh DB | partial/old schema | start from an empty DB; chain is `0000 → 0007` (verified) |
| CI `check_migrations` fails | model changed without a migration | generate a migration for the reported table/column |
| Admin AI account create 400 "base_url…" | SSRF guard | use http(s) public host, or add internal host to `AI_BASE_URL_ALLOWLIST` |
| Mini App keyboard button missing | bot started without https `MINIAPP_URL` | set `MINIAPP_URL` + restart bot; user presses /start |

## Useful commands
```bash
docker compose logs -f api worker beat bot          # tail services
docker compose exec api alembic current             # migration head
docker compose exec api python -m scripts.check_migrations
curl -s https://$DOMAIN/health/ready | jq
curl -s https://$DOMAIN/health/providers | jq
BASE_URL=https://$DOMAIN scripts/smoke_test.sh
```

## Logs
Structured JSON (structlog). With the monitoring stack, query in Grafana/Loki:
`{container=~".*api.*"} |= "error"`. Key events: `payment.*`, `refund_job.*`,
`ai.*`, `bot.*`.
