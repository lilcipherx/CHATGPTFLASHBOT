# Environment variables

Copy `.env.example` → `.env` (prod) or `.env.staging.example` → `.env.staging`.
The app **fails closed** at startup on insecure secrets when a public webhook
deploy is configured (`BOT_MODE=webhook` + `WEBHOOK_BASE_URL`) — see
`core/config.py::_require_prod_secret`.

## Core
| Var | Default | Notes |
|-----|---------|-------|
| `BOT_TOKEN` | — | from @BotFather. Required. |
| `BOT_MODE` | `polling` | `polling` (dev) / `webhook` (prod). |
| `WEBHOOK_BASE_URL` | — | public HTTPS base; required for webhook mode. |
| `WEBHOOK_SECRET` | derived | Telegram secret-token; auto-derived from bot token if empty. |
| `MINIAPP_URL` | — | public HTTPS Mini App URL. |
| `ENV` | `dev` | `dev`/`test`/`staging`/`prod`. |
| `DEV_WEBAPP_BYPASS` | `false` | DEV ONLY — accept unsigned initData. Never enable on a reachable host. |

## Infra
`DATABASE_URL`, `REDIS_URL` (`memory://` for fakeredis), `DB_POOL_SIZE`,
`DB_MAX_OVERFLOW`, `DB_PGBOUNCER`, `STUCK_JOB_MINUTES`,
`S3_ENDPOINT`/`S3_KEY`/`S3_SECRET`/`S3_BUCKET`/`S3_PUBLIC_URL` (MinIO/S3 uploads).

## AI providers
`OPENAI_API_KEY` + `OPENAI_BASE_URL`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`,
`OPENROUTER_API_KEY` (+ `OPENROUTER_FREE_TIER`), `DEEPSEEK_API_KEY`,
`PERPLEXITY_API_KEY`, media keys (`KLING_API_KEY`, …). Point any OpenAI-compatible
var at the **mock server** (`http://localhost:8088/v1`) for keyless dev.

## Payments
`YOOKASSA_SHOP_ID`/`YOOKASSA_SECRET`, `STRIPE_SECRET`/`STRIPE_WEBHOOK_SECRET`,
`TRIBUTE_API_KEY` + `TRIBUTE_API_VERIFIED` (inert until verified),
`STARS_TO_RUB`/`STARS_TO_USD`.

## Security / admin
| Var | Notes |
|-----|-------|
| `ADMIN_JWT_SECRET` | strong random; startup fails on the default in prod. |
| `ENC_SECRET` | encrypts stored AI keys at rest; required in prod. |
| `ADMIN_IP_ALLOWLIST` | comma CIDRs; empty = open (dev). |
| `CORS_ORIGINS` | exact origin(s) in prod; `*` rejected on public deploy. |
| `METRICS_TOKEN` | gate `/metrics` if reachable. |
| `AI_BASE_URL_ALLOWLIST` | host suffixes admins may set as AI `base_url` (SSRF guard). |
| `SENTRY_DSN` | error reporting (bot + api). |

## Prod / ops
`DOMAIN`, `ADMIN_ALLOW_IP` (Caddy), `BACKUP_INTERVAL_SECONDS`,
`BACKUP_RETENTION_DAYS`, `BACKUP_WEBHOOK_URL`, `GRAFANA_ADMIN_PASSWORD`,
`ALERT_BOT_TOKEN`.

> Full annotated list with inline guidance: `.env.example`.
