# Deployment

## Prerequisites
- A host with Docker + Docker Compose.
- A domain with DNS A/AAAA → the host (`DOMAIN`), for automatic TLS via Caddy.
- A Telegram bot token (@BotFather). For the Mini App: BotFather → Bot Settings →
  Configure Mini App → enable + set URL to `https://$DOMAIN`.

## 1. Configure
```bash
cp .env.example .env
# Fill: BOT_TOKEN, DOMAIN, WEBHOOK_BASE_URL=https://$DOMAIN, MINIAPP_URL=https://$DOMAIN,
#       BOT_MODE=webhook, ENV=prod, strong ADMIN_JWT_SECRET + ENC_SECRET,
#       CORS_ORIGINS=https://$DOMAIN, ADMIN_ALLOW_IP, payment + AI keys.
```
The app refuses to start on default/insecure secrets in a public webhook deploy.

## 2. Build the SPAs
```bash
(cd miniapp && npm ci && npm run build)
(cd admin   && npm ci && npm run build)
```

## 3. Launch (prod stack)
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```
Brings up: postgres, pgbouncer, redis, omniroute, minio, **bot** (webhook),
**api** (gunicorn, 4 workers), **worker**, **beat** (1), **caddy** (TLS +
admin/omniroute IP allow-lists), **backup**.

## 4. Migrate + seed
```bash
docker compose exec api alembic upgrade head
docker compose exec api python -m scripts.seed_catalogs       # effects/templates
docker compose exec api python -m scripts.create_admin        # superadmin
```

## 5. Verify
```bash
BASE_URL=https://$DOMAIN scripts/smoke_test.sh
curl -s https://$DOMAIN/health/ready
```
Admin panel: `https://admin.$DOMAIN` (IP-allow-listed). Mini App: open the bot.

## Observability (optional but recommended)
```bash
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d
```
Grafana on `:3000` (firewall it). See [MONITORING.md](MONITORING.md).

## Upgrades
1. `git pull` → rebuild SPAs → `docker compose ... build`.
2. `alembic upgrade head` (run `python -m scripts.check_migrations` in CI first).
3. `docker compose ... up -d` (rolling; `restart: always`).
4. `scripts/smoke_test.sh`.

## Scaling
- API: `docker compose up -d --scale api=N` (stateless, behind Caddy).
- Workers: `--scale worker=N`. **Keep `beat` at 1** (it owns cron).
- DB pressure: set `DB_PGBOUNCER=true` and point `DATABASE_URL` at `pgbouncer:6432`.

## Staging
See [ENV.md](ENV.md) + `docker-compose.staging.yml`:
```bash
docker compose -p aibot-staging --env-file .env.staging \
  -f docker-compose.yml -f docker-compose.staging.yml up -d
BASE_URL=http://localhost:8001 scripts/smoke_test.sh
```

## Rollback
Re-deploy the previous image tag (`ghcr.io/<repo>:<version>`), then
`alembic downgrade <prev_revision>` only if a migration must be reversed
(most are additive/idempotent). Restore data from backup if needed
([BACKUP.md](BACKUP.md) / [RESTORE.md](RESTORE.md)).
