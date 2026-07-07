# Changelog

All notable changes to this project. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); dates are UTC.

## [Unreleased]

### Added — analytics (ТЗ §8)
- **Funnel, retention & content analytics** — completing the §8 metrics set
  (revenue/DAU/ARPU/conversion + traffic/reports/CSV already shipped). Three new
  read-only admin endpoints over existing tables (no migration): `/analytics/funnel`
  (signup-cohort registered→activated→purchased→repeat), `/analytics/retention`
  (rolling D1/D7/D30 over the windowed cohort, documented proxy), `/analytics/content`
  (top services + model variants by job count). Rendered on the existing Analytics
  page (funnel + content bar panels, retention metric cards). Tests +3.

### Added — Mini App (ТЗ §4)
- **«Скачать» (download) button** on a finished result (ТЗ §4 «кнопка Скачать к
  результату»). Uses Telegram's native `downloadFile` (Bot API 8.0+) for a real save
  dialog, falling back to opening the file URL on older clients. New `download` i18n
  key in all 8 locales.

### Added — operations, generation & bot (ТЗ §8, §5, §3)
- **`/search` and `/avatar` command aliases** (ТЗ §3 «/s→/search», «/ava→/avatar»):
  both new names now work alongside the originals.
- **Internet-search system prompt is admin-editable** (ТЗ §3 «улучшить поиск из
  админки») — `search.system_prompt` in business config, replacing the hard-coded
  prompt; blank falls back to the default. Tests +1.
- **Premium queue priority** (ТЗ §8 «приоритет очереди для Premium»). Generation
  jobs from Premium users now jump the ARQ queue: `enqueue(..., priority=True)`
  back-dates the job's `_defer_until` so it sorts ahead of free users' jobs (FIFO
  preserved within each class). Decided centrally in `enqueue_or_refund` /
  `is_priority_job` from the job owner's premium status + a live
  `queue.premium_priority_enabled` flag (on by default); wired into bot + Mini App
  generation paths. No migration. Tests +5.
- **Documents service is now admin-managed** (ТЗ §5/§1 «документы — параметры из
  админки»). Added a `documents` feature flag (on/off, like music/video) and a
  live-editable cost (`documents.cost`, default 3) read by the bot, replacing the
  hard-coded `DOC_COST` constant in both the document and chat-followup paths.
  Tests +2.

### Added — AI routing (ТЗ §2)
- **Router-container management** («управление контейнерами роутеров»). New
  superadmin-only admin API (`/admin/routers …` — list/status/logs/start/stop/
  restart) driving `docker compose` for the self-hosted LiteLLM router, plus an
  embedded panel on the AI-routing page. Hard-gated: off by default
  (`ROUTER_MGMT_ENABLED`), fixed service allowlist (`ROUTER_SERVICES`), fixed argv
  (no shell), per-call timeout, every action audited. This closes §2. The admin SPA
  also gains the routing columns/inputs for weight, latency, spend, and limits.
- **Per-account spend limits** («лимиты трат»). `ai_accounts.spend_limit_micros`
  (migration `0020`, 0 = unlimited) is a hard cap: when reached, the account is
  sidelined from routing (`_is_available`) until the admin raises the cap or resets
  spend via a new superadmin `POST /ai/accounts/{id}/reset-spend`. Exposed in the
  accounts API (`spend_limit_*`, `over_budget`) + export/import.
- **Provider spend / cost accounting** («расход, себестоимость»). Each `ai_models`
  row gains an admin-set `cost_micros` (provider cost per request, micro-USD);
  `ai_accounts` accrues `spend_micros` per successful request (migration `0019`).
  The admin accounts/health API exposes `spend_micros` + a display `spend_usd`.
- **Per-account latency/uptime tracking** («latency/uptime»). `ai_accounts` gains
  `last_latency_ms` + an EMA `avg_latency_ms` (migration `0018`), recorded by
  `mark_success(latency_ms=…)` from the timed synchronous text path only (media
  gateways long-poll and pass None). The accounts/health API adds `avg_latency_ms`,
  `last_latency_ms`, and a `success_rate` uptime proxy.
- **Weighted load-balancing across accounts** («балансировка по весам»). Added an
  `ai_accounts.weight` column (migration `0017`); `candidate_accounts` now
  weight-shuffles accounts that share a `(tier, priority)` via Efraimidis–Spirakis
  sampling (traffic ∝ weight) while keeping pool→fallback tier order and strict
  ordering across distinct priorities. Exposed in the accounts API.

### Added — engagement (ТЗ §7)
- **Daily-bonus auto-reminder** — the 4th auto-notification type from ТЗ §7
  («бонус»), completing the set alongside premium-expiry / low-balance / win-back.
  A new `bonus_available` channel (off by default, admin-tunable via
  `notifications.bonus_available_enabled`) nudges users whose daily-bonus streak is
  at risk — claimed yesterday but not yet today — so they don't break it. Same
  Redis dedupe + best-effort dispatch as the other channels; no migration. Tests +2.

### Added — monetization (ТЗ §6)
- **Premium auto-renewal now charges for real.** Previously the daily cron selected
  opted-in users but the charge was a stub (no saved-token model). Added a
  gateway-agnostic `payment_methods` token store (migration `0016`): the card is
  vaulted at the original subscription checkout (YooKassa `save_payment_method`;
  Stripe customer + `setup_future_usage=off_session`), captured from the webhook,
  and charged off-session at renewal — extending the sub via the existing idempotent
  `activate_subscription`. Renews at the live one-month price for the user's tier;
  declines leave the subscription untouched. Stars/СБП/Crypto (no off-session
  charge) are skipped. Tests: +3 (autorenew charge path, payment-method store).

## [production-hardening pass] (2026-06-20)

### Security (fixed)
- **Mini App moderation bypass**: `effect_generate` now runs content moderation
  on the user prompt before any work (parity with all bot paths).
- **SSRF**: admin-set AI account `base_url` is validated (http(s) only,
  private/loopback IPs rejected, optional `AI_BASE_URL_ALLOWLIST`).
- **Payment loss on transient webhook errors**: verification now distinguishes
  retryable failures (→ 503, gateway retries) from forgeries (→ 200).
- **Config fails closed** on default secrets / wildcard CORS when a public
  webhook deploy is configured, even at `ENV=dev`.
- **Uploads** validated by content (magic bytes) for banners; saved only after a
  successful charge (no orphaned objects); aggregate size cap added.

### Performance / scale
- Composite indexes on `generation_jobs` (history + sweep) and `pg_trgm` search
  indexes on `users.username/phone` (migration `0007`).

### Added — infrastructure
- **Local mock AI server** (`scripts/mock_ai_server.py`) — run the full stack
  with no real keys (OpenAI-compatible + Kie/MuAPI shapes).
- **Health**: `/health/ready` (DB+Redis), `/health/providers`; richer `/metrics`.
- **CI/CD**: GitHub Actions (lint, tests+coverage, migration-drift check,
  frontend build+test matrix, pip-audit/bandit, Docker build) + tag-driven GHCR
  release + Dependabot.
- **Load tests**: k6 (smoke/load/spike/soak) + Locust + runner.
- **Monitoring**: Prometheus + Alertmanager + Grafana (dashboard) + Loki/Promtail
  + postgres/redis exporters + alert rules.
- **Backup/restore**: integrity-checked backups with checksums + S3/notify;
  destructive-guarded restore; automated restore-drill; DB maintenance SQL.
- **Staging**: `docker-compose.staging.yml` + `.env.staging.example` + smoke test.
- **Frontend tests**: Vitest (miniapp + admin) + Playwright e2e scaffold.
- **Docs**: ARCHITECTURE, DEPLOYMENT, ENV, SECURITY, MONITORING, BACKUP, RESTORE,
  CICD, TROUBLESHOOTING, RUNBOOK, API, CONTRIBUTING.

### Tests
- Backend 113 → **129** passing (audit regressions + mock-server contracts).
- Frontend: miniapp 5 + admin 3 Vitest tests passing; both SPAs build clean.

## [0.1.0] — initial build
- Multi-model AI Telegram bot + Mini App + admin panel (phases 0–7): aiogram 3,
  FastAPI, SQLAlchemy 2 async, PostgreSQL, Redis, ARQ, MinIO; payments
  (Stars + YooKassa + Stripe + Tribute); 8 locales; multi-backend AI routing.
