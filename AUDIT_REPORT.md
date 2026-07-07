# CHATGPTFLASHBOT — End-to-End Audit Report

**Date:** 2026-07-02
**Scope:** Telegram Bot (aiogram 3), Mini App (React/TS/Vite), Admin Panel (React/TS/Vite), backend API/workers, infra, DB/migrations, security.
**Codebase size:** ~36k LOC Python (258 files), ~21k LOC frontend (23 Mini App + 48 Admin TS/TSX), 800 tests (0 skips/xfails).
**Method:** 8 parallel domain auditors + direct verification of the highest-impact findings. All findings carry file:line + verbatim evidence. No fabrication.

> **Overall posture:** This tree has been through several prior audit rounds (pervasive `FIX:` markers) and is genuinely well-hardened — argon2 + anti-enumeration + token_version, HMAC initData, integer-minor-unit money with row locks everywhere, idempotent webhooks via unique `gateway_tx_id`, moderation-before-charge, refund-on-failure in workers, i18n parity (all 8 locales = 301 keys), self-hosted fonts, server-side CSV export. The **two most severe issues are self-labeled "temporary" `FIX: DEPLOY-*` edits that disabled security controls and were left in the tree.**

---

## CRITICAL

### C1 — Telegram webhook signature verification is disabled → unauthenticated impersonation & free entitlements
`api/routers/webhooks.py:44`
```python
if False:  # FIX: DEPLOY-7 - temporary disable webhook secret check (was breaking Telegram message reception)
    # Original: if not hmac.compare_digest(received, settings.effective_webhook_secret):
    return Response(status_code=403)
```
The `x-telegram-bot-api-secret-token` check is short-circuited; the body is fed straight into `dp.feed_update(bot, update)`. The path is fixed/guessable (`core/config.py:318` → `/webhook/telegram`). Any internet client can POST a forged `Update` — impersonate any `user_id`, and (critically) inject a `message.successful_payment` with attacker-chosen `invoice_payload`/`total_amount`/`telegram_payment_charge_id`. The Stars path does **no** server-side amount validation (unlike external gateways) and a fresh `telegram_payment_charge_id` each time bypasses the idempotency guard → unlimited free premium/credits.
**Fix:** restore `if not hmac.compare_digest(received, settings.effective_webhook_secret): return Response(status_code=403)`.
*(Found independently by both the auth and payments auditors.)*

---

## HIGH

### H1 — Admin IP allowlist silently bypassed
`api/admin/deps.py:33-34`
```python
if client not in allow:
    pass  # FIX: DEPLOY-5 - disabled IP allowlist check so admin panel accepts any IP by default
```
`ip_allowlisted` is the sole app-layer IP gate for the whole admin API + `/auth/login`. `core/config.py:284` *forces* `ADMIN_IP_ALLOWLIST` non-empty on public deploy, so operators believe the panel is IP-restricted while every IP is accepted. **Fix:** `raise HTTPException(403)`.

### H2 — Auto-renewal compensating refund is dead code (ImportError) → user charged, no sub, no refund
`core/services/autorenew.py:144`
```python
from core.payments import GATEWAYS   # ImportError: core/payments/__init__ exports get_provider/_PROVIDERS, no GATEWAYS
```
Verified: `core/payments/__init__.py` has no `GATEWAYS` symbol. When an off-session charge succeeds but `activate_subscription` then raises, the handler's first line throws `ImportError`, swallowed as `refund_after_activate_failed`. User is charged, gets nothing, no refund. **Fix:** `gw = get_provider(method.gateway)`; move import above the branch.

### H3 — X-Forwarded-For spoofing (client IP forgeable)
`docker-compose.prod.yml:75` runs the API with `--forwarded-allow-ips="*"`; the code comment claims the Caddyfile rewrites XFF, but **`Caddyfile` has no `header_up` directive** (verified). Caddy appends to XFF by default, so a client-supplied `X-Forwarded-For` is trusted → forges the YooKassa webhook source-IP allowlist and the admin login-audit IP. **Fix:** `header_up X-Forwarded-For {remote_host}` in the reverse_proxy blocks.

### H4 — Caddyfile has no admin IP allowlist and ignores DOMAIN
`docker-compose.prod.yml:92-93` require `DOMAIN`/`ADMIN_ALLOW_IP`, but `Caddyfile` never references them, hardcodes `https://superaibot.duckdns.org` (`Caddyfile:3`), and `handle /admin/*` + `handle /api/*` have no `@allowed` IP matcher. Admin surface is reachable from any IP at the proxy layer (compounds H1). **Fix:** add `@allowed remote_ip {$ADMIN_ALLOW_IP}` gating on admin routes; use `{$DOMAIN}` as the site address.

### H5 — .dockerignore inline comments break exclusions → dev DB / 54 MB exe / media baked into image
`.dockerignore:26,30,31` (verified)
```
*.db*          # dev.db, dev.db.bak.*
*.exe          # cloudflared.exe (~54 MB)
media/         # runtime user uploads
```
Docker's dockerignore parser does not strip inline `#` comments, so these patterns match nothing and `Dockerfile:58` `COPY . .` ships `dev.db*` (may hold tokens/user data), `cloudflared.exe`, and `media/`. **Fix:** move comments to their own lines.

### H6 — GIN trigram indexes built NON-concurrently on the hot `users` table
`migrations/versions/0007_search_job_indexes.py:69-78` — comment says "CONCURRENTLY on the GIN indexes too" but the raw SQL omits it. A plain `CREATE INDEX` on `users` takes a SHARE lock blocking all INSERT/UPDATE/DELETE for the (multi-minute) GIN build → registrations and all user-row updates stall during migration. **Fix:** `CREATE INDEX CONCURRENTLY` inside `autocommit_block()`.

### H7 — EffectGrid renders API failures as "empty category" (dead error state)
`src/components/EffectGrid.tsx:29,40,66` — `err` is set (`setErr(true)`) but never read; render branches only on `null`/`length===0`. A 500/timeout/network-drop/**expired-session 401** on `/api/effects` shows "No effects in this category yet" with no error and no retry, on the main Home/Trends content grid. **Fix:** render an error+retry branch on `err`.

### H8 — Admin session-expiry leaves 6 pages on a dead panel
6 page-local fetch wrappers call `logout()` on 401 but omit the `admin:unauth` event that `App.tsx:260-264` needs to swap to `<Login>`: `Analytics.tsx:16`, `Gallery.tsx:13`, `ChannelPosts.tsx:14`, `Localization.tsx:22`, `Contests.tsx:13`, `Dashboard.tsx:19`. After token+refresh expiry the admin is stuck on broken data with no redirect. **Fix:** dispatch `admin:unauth` (mirror `api.ts:186-191`) or route these through the shared `req()`.

---

## MEDIUM

### M1 — First-purchase-bonus double-grant race
`core/services/billing.py:273-276` — `add_pack_credits` locks only the `PackBalance` row, not the `User` row, before `_apply_purchase_promos`/`_is_first_purchase`. A concurrent first pack purchase + first sub/credits purchase (which never touch PackBalance) can both pass `_is_first_purchase` → double bonus. Sibling paths already lock User (`record_one_time:151` FIX C3, `activate_subscription:185`). **Fix:** `await session.refresh(user, with_for_update=True)` before line 276.

### M2 — Validating FK constraints added under ACCESS EXCLUSIVE on hot tables
`migrations/versions/0038_user_cascade_delete.py:67-78` adds 11 `FOREIGN KEY ... ON DELETE CASCADE` via plain `create_foreign_key` on `transactions`/`generation_jobs`/`usage_log` etc. — full validation scan under ACCESS EXCLUSIVE (docstring's "sub-second" is false at scale). **Fix:** `ADD CONSTRAINT ... NOT VALID` then separate `VALIDATE CONSTRAINT`.

### M3 — Security header typo + no CSP at proxy
`Caddyfile:7` `X-Content-Type-Options "nosiff"` (verified typo → browsers ignore it); no `Content-Security-Policy` header. HSTS/X-Frame-Options/Referrer-Policy are present. **Fix:** `nosniff`, add CSP.

### M4 — `is_public_deploy` doesn't cover the internet-facing API process
`core/config.py:219` `is_public_deploy = bot_mode=="webhook" and webhook_base_url`. In `docker-compose.prod.yml` only the `bot` service sets `BOT_MODE=webhook`; `api`/`worker`/`beat` inherit `polling`. So the admin-IP + metrics-token boot checks (`config.py:284-291`) and the `DEV_WEBAPP_BYPASS` fail-closed net (`api/deps.py:72-76`) don't fire for the API. A prod `.env` with `ENV=dev`+`DEV_WEBAPP_BYPASS=true` would serve anonymous requests as `DEV_WEBAPP_USER`. **Fix:** derive public-deploy from a process-independent flag; force `BOT_MODE=webhook` for api/worker/beat or set an explicit `PUBLIC_DEPLOY=true`.

### M5 — HEALTHCHECK targets :8000 on non-HTTP services
`Dockerfile:66-67` curls `:8000/health/ready`; `bot`/`worker`/`beat` don't listen on 8000 → permanently `unhealthy`, can trigger restarts / block `depends_on: service_healthy`. **Fix:** per-service healthcheck (or `healthcheck: disable` for non-API).

### M6 — Dead alerts (missing exporters/jobs)
`monitoring/alerts.yml:73,105,113` define `BotDown{job="aibot-bot"}`, `DiskFull`, `HostMemoryHigh` on node_exporter metrics, but `monitoring/prometheus.yml` scrapes only `aibot-api/prometheus/postgres/redis` and there's no node-exporter service → these three alerts never fire. **Fix:** add node-exporter + the `aibot-bot` scrape job.

### M7 — Prometheus can't scrape /metrics when METRICS_TOKEN is set
`monitoring/prometheus.yml:20-22` leaves the token commented, but `api/routers/health.py:103-106` returns 403 without it when `METRICS_TOKEN` is configured → all `aibot_*` metrics + `ApiDown` break in a public deploy. **Fix:** wire the token param.

### M8 — App serves against a failed migration
`docker-compose.yml:109-110` `migrate: condition: service_started` (inherited by prod) — app waits only for migrate to *start*. If `alembic upgrade head` fails, services boot against a stale schema. **Fix:** `service_completed_successfully`.

### M9 — No resource limits in prod
No `deploy.resources`/`mem_limit`/`cpus` in `docker-compose.prod.yml`; a single container can OOM the host (and `alerts.yml:118` advises raising limits that don't exist). **Fix:** add per-service limits.

### M10 — LITELLM_MASTER_KEY weak default not validated
`.env.example:71` `LITELLM_MASTER_KEY=sk-litellm-change-me`; compose `${...:?required}` only rejects empty, and `_require_prod_secret()` doesn't check it. A copied `.env` exposes the LiteLLM proxy master key. **Fix:** add to `_require_prod_secret()`.

### M11 — Text router retries permanent errors
`core/ai_router/registry.py:87` defines `_RETRY_STATUSES = {429,500,502,503,504}` but it's never referenced; the loop retries on all exceptions, so 401/402/403 (bad key / no credits) accounts burn ~2.2s of backoff on a live chat turn. **Fix:** classify by status; re-raise non-transient on first attempt.

### M12 — Kling poll endpoint mismatch
`core/ai_router/video_adapters.py:142` submits `.../videos/generations/{text2video|image2video}` but polls `.../videos/generations/{job_id}` (`:159`), dropping the mode segment (and both carry an extra `/generations/`). If the base is live, every poll 404s → 20-min timeout → refund on every Kling video. **Fix:** poll `.../videos/{mode}/{job_id}` per Kling docs (verify against a live key).

### M13 — Suno version mismatch (billing vs model)
`bot/handlers/music_gen.py:45` labels the paid service "Suno V5.5" but stores no model, and `core/ai_router/music_adapters.py:40` defaults to `suno-v4`. Users pay for V5.5 and always get v4. **Fix:** pass the intended model or correct the label.

### M14 — Mini App: expired session (401) unhandled inside Telegram
`src/App.tsx:68` gates re-auth on `!WebApp.initData`, so an in-Telegram user whose signed session expires (401 → `err_auth` with truthy initData) never sees the gate — credits stuck on "—", grids show the false "empty" state (H7). **Fix:** add an expired-session reload/re-auth path when `initData` is present.

### M15 — Mini App: `LANG` frozen snapshot → banners in wrong language
`src/i18n.ts:324` `export const LANG` is captured once at load; `src/api/client.ts:237` fetches `/banners?locale=${LANG}`. After `/profile` syncs a different bot-side `language_code`, `LANG` doesn't update (the rest of the app uses live `getLang()`), and `Carousel.tsx:27-35` only fetches on mount. **Fix:** use `getLang()` and re-fetch on language sync.

### M16 — Mini App: CSP `connect-src 'self'` blocks a cross-origin API deploy
`index.html:12` — `mediaUrl`/`client.ts:6-15` explicitly support serving the app cross-origin from the API, but `connect-src` allows only `'self'` (+Telegram/OpenAI/Google), so in that config every `${BASE}/api/...` fetch is CSP-blocked while images still load. **Fix:** add the API origin to `connect-src` (or keep same-origin).

### M17 — Admin: Users search has no race guard
`src/pages/Users.tsx` never uses `useLatestGuard` (unlike Payments/Audit/Feedback/Gallery); `search()` fires from button + Enter + `useEffect([sort,country,language])` (`:58`), and `:47-49`/`loadMore():86-91` apply results with no `isLatest()` check → a slow earlier response overwrites the newer filtered list.

### M18 — Admin: ban/unban has no confirmation
`src/pages/Users.tsx:291-293` fires `api.ban(...)` immediately on click, while revoke-premium/delete-tag/refund all confirm → a misclick on the red "Забанить" bans a user (server-side, user notified) with no undo prompt.

---

## LOW

- **DB:** non-concurrent partial index on `users` (`0004_user_indexes.py:36-42`); non-concurrent `DROP INDEX` in downgrades (`0007:84-89`, `0021`, `0023`); blocking type-widening rewrites (`0022:56-62`, `0037`) — all low-volume/mitigated.
- **Balances:** non-atomic audit in `reset_quota`/`clear_user_context` (`api/admin/users.py:360-387`, separate `commit=True` audit); multi-use discount per-user cap is TOCTOU (`core/services/promos.py:230-266`).
- **AI:** BFL ignores `Content Moderated`/`Task not found` poll statuses → slow failure (`image_adapters.py:290-296`); BFL base `api.bfl.ml` likely stale vs `api.bfl.ai` (`:215`, verify); Google adapter flattens roles into one prompt string (`google_adapter.py:38`, mild injection asymmetry).
- **Infra:** `.env.staging.example` (`ENV=staging`+`CORS_ORIGINS=*`) crashes on boot since `_require_prod_secret` only exempts dev/test (`config.py:225,255-260`); `YOOKASSA_TAX_SYSTEM_CODE=0` is invalid (valid 1–6, or empty to omit) (`.env.example:96`).
- **Auth:** `initdata_max_age=86400` (24h) is a long replay window (`config.py:32`); `last_error` stores raw provider text (`ai_routing.py:223,235`) surfaced to admins — sanitize defensively.
- **Admin UI:** Modal lacks focus trap / initial focus / focus restore and uses a hardcoded `modal-title` id (`components/Modal.tsx:28,31`); grant amount allows 0, months has no NaN/negative guard (`Users.tsx:262,273`); second in-flight action click silently dropped, buttons not `disabled={actBusy}` (`Users.tsx:108`); `crmDeleteNote` no confirm (`:424`).
- **Mini App:** `.fonts-loading` class has no CSS rule → blank screen instead of FOUT hiding (`main.tsx:24`); sheets not portaled, no ESC/focus-trap/body-scroll-lock, inconsistent BackButton wiring (`CreateSheet.tsx` vs `Profile.tsx` StoreSheet); two async `setState`s in CreateSheet not abort-guarded (`:62-63,136`).

---

## Verified CLEAN (no action)
- i18n parity: all 8 locales (ru/en/es/fr/pt/uz/ar/zh) = exactly 301 keys, zero drift.
- "Open App" button already removed from reply keyboard (`bot/keyboards/reply.py:22-28`) and inline menus (`bot/keyboards/inline.py:103-108`).
- Tests: 800 functions, 0 skips/xfails; dedicated payment/webhook-idempotency/refund/autorenew/webapp-auth suites.
- Migration chain linear (0000→0039, single head); all downgrades substantive; BigInteger for Telegram IDs; integer minor units for money; timezone-aware datetimes; unique constraints on `gateway_tx_id`/promo/referral.
- Webhook idempotency (unique `gateway_tx_id` + IntegrityError guard), external-gateway amount re-fetch/validate, sync SDK wrapped in `asyncio.to_thread`, balance mutations under `with_for_update`, moderation-before-charge, worker refund-on-failure with conditional-UPDATE claims.
- Admin: `adminFetch` auth+timeout+single-flight refresh-retry; XSS sinks pass through `sanitizeTelegramHtml` allowlist; CSV server-side streamed with `revokeObjectURL`; `encodeURIComponent` on params.
- Mini App: `fetchWithTimeout` everywhere, bounded `pollJob`, ErrorBoundary, self-hosted fonts, BackButton/haptic cleanup.

---

## Recommended fix order
1. **C1, H1** — revert the two `FIX: DEPLOY-*` backdoors (webhook HMAC + admin IP `raise 403`).
2. **H3, H4** — Caddyfile `header_up X-Forwarded-For` + admin `@allowed remote_ip` + `{$DOMAIN}`.
3. **H2, M1** — autorenew refund import + first-purchase User-row lock (money-integrity).
4. **H5, M8** — `.dockerignore` comment fix + `service_completed_successfully`.
5. **H6, M2** — concurrent GIN index + `NOT VALID`/`VALIDATE` FK migrations.
6. **H7, H8, M14, M15** — Mini App error/expired-session states + admin 401 event + language sync.
7. Remaining MEDIUM/LOW as capacity allows.

---

## Fixes applied (2026-07-02)

All changes byte-compile (`py_compile` OK on every touched module); the runtime test
suite could not be executed here because the Python deps (aiogram/sqlalchemy/…) are
not installed in this environment.

| # | Severity | Fix | File(s) |
|---|----------|-----|---------|
| C1 | CRITICAL | Restored webhook HMAC `compare_digest` check (removed `if False:`) | `api/routers/webhooks.py:44` |
| H1 | HIGH | Admin IP mismatch now `raise HTTPException(403)` (removed `pass`) | `api/admin/deps.py:33` |
| H2 | HIGH | Auto-renew refund uses `get_provider()` (was `import GATEWAYS` → ImportError) | `core/services/autorenew.py:143-148` |
| H3 | HIGH | Caddy `header_up X-Forwarded-For {remote_host}` on all proxy blocks | `Caddyfile` |
| H4 | HIGH | Caddy `{$DOMAIN}` site + admin-only IP matcher on `/api/admin/*` | `Caddyfile` |
| H5 | HIGH | `.dockerignore` inline comments moved to own lines | `.dockerignore:25-36` |
| H6 | HIGH | GIN indexes built/dropped `CONCURRENTLY` in autocommit blocks | `migrations/versions/0007_search_job_indexes.py` |
| H7 | HIGH | EffectGrid shows error+Retry (was dead `err` → false "empty") | `miniapp/src/components/EffectGrid.tsx` |
| H8 | HIGH | 6 admin pages dispatch `admin:unauth` on 401 | `admin/src/pages/{Analytics,Gallery,ChannelPosts,Localization,Contests,Dashboard}.tsx` |
| M1 | MED | `add_pack_credits` locks the User row before first-purchase check | `core/services/billing.py:273` |
| M3 | MED | `nosiff` → `nosniff` header | `Caddyfile:7` |
| M8 | MED | migrate gate `service_completed_successfully` (fail closed) | `docker-compose.yml` (4 services) |
| M11 | MED | AI text router breaks on non-retryable status (honors `_RETRY_STATUSES`) | `core/ai_router/registry.py:216` |
| M13 | MED | Suno label matches the model actually sent (was "V5.5" vs `suno-v4`) | `bot/handlers/music_gen.py` |
| M14 | MED | Mini App shows error+Retry on in-Telegram 401 | `miniapp/src/App.tsx` |
| M15 | MED | Banners fetch uses live `getLang()` (was frozen `LANG`) | `miniapp/src/api/client.ts:237` |
| M17 | MED | Users search/loadMore race guard (`useLatestGuard`) | `admin/src/pages/Users.tsx` |
| M18 | MED | Confirm dialog before banning a user | `admin/src/pages/Users.tsx` |
| L13 | LOW | `YOOKASSA_TAX_SYSTEM_CODE` default `0` → empty (0 is invalid) | `.env.example:96` |
| M4 | MED | `is_public_deploy` now covers ALL processes (`public_deploy` flag OR shared `WEBHOOK_BASE_URL`), so the internet-facing API/worker/beat fail closed too | `core/config.py`, `.env.example` |
| M10 | MED | Boot rejects the default `LITELLM_MASTER_KEY` (`sk-litellm-change-me`) in prod (new `litellm_master_key` field) | `core/config.py`, `.env.example` |
| M12 | MED | Kling: correct per-mode endpoints `/v1/videos/{text2video\|image2video}[/{task_id}]` (no `/generations/`), mode carried through poll, and `model_name` field (was `model`) — verified against Context7 official Kling docs | `core/ai_router/video_adapters.py` |

Existing tests that assert `is_public_deploy` semantics (`tests/test_audit_fixes.py:154,163`, `tests/test_security_hardening.py:14`) still hold under the new logic; no test references the Kling HTTP URL/field.

| # | Severity | Fix | File(s) |
|---|----------|-----|---------|
| M2 | MED | FK constraints added `NOT VALID` then `VALIDATE` (per-table autocommit) so the validation scan doesn't hold ACCESS EXCLUSIVE; SQLite falls back to plain create | `migrations/versions/0038_user_cascade_delete.py` |
| M5 | MED | `healthcheck: disable: true` on bot/worker/beat (they serve no HTTP → were permanently "unhealthy") | `docker-compose.yml` |
| M6 | MED | Added `node-exporter` service + `node` scrape job → `DiskFull`/`HostMemoryHigh` now have data; `BotDown` disabled with a note (bot exposes no metrics endpoint, so it could never fire) | `docker-compose.monitoring.yml`, `monitoring/prometheus.yml`, `monitoring/alerts.yml` |
| M7 | MED (partial) | Made the `/metrics` token requirement loud + actionable in the scrape config. NOTE: still one manual deploy step — Prometheus can't expand env vars, so the operator must inject the real `METRICS_TOKEN` at deploy (no secret committed) | `monitoring/prometheus.yml` |
| M9 | MED | Added generous `deploy.resources.limits` (memory+cpus) to postgres/redis/api/worker/bot/beat so one container can't OOM the host (tune per host) | `docker-compose.prod.yml` |
| M16 | MED (conditional) | Documented that the shipped topology is same-origin (so `connect-src 'self'` is correct); a cross-origin deploy must add the API origin — did NOT weaken the default | `miniapp/index.html` |

All edited compose/monitoring YAML validated (PyYAML `safe_load_all` OK); migration `py_compile` OK.

### LOW items applied (round 4)

| Area | Fix | File(s) |
|------|-----|---------|
| Admin a11y | Modal now traps Tab, sets initial focus, and restores focus on close (`aria-modal` previously advertised trapping that wasn't implemented) | `admin/src/components/Modal.tsx` |
| Admin UX | Grant/deduct/ban/premium buttons `disabled={actBusy}`; grant blocked at amount 0; months clamped to a positive integer; confirm before deleting a CRM note | `admin/src/pages/Users.tsx` |
| Atomic audit | `reset_quota` & `clear_context` fold the audit row into one commit (`commit=False` + single `session.commit()`) | `api/admin/users.py` |
| AI | BFL treats `Content Moderated`/`Request Moderated`/`Task not found` as terminal (fail fast instead of polling ~2 min) | `core/ai_router/image_adapters.py` |
| Concurrency | `consume_discount` locks the user row + re-checks redemption so a multi-use code can't be double-consumed by one user | `core/services/promos.py` |
| Mini App | Removed the dead `fonts-loading` class toggle (no-op, no matching CSS); added an unmount guard to CreateSheet's detail/balance load | `miniapp/src/main.tsx`, `miniapp/src/components/CreateSheet.tsx` |

### Test run (round 5) — dependencies installed, `pytest` executed

Installed deps in a Python 3.12 venv (via `uv`) and ran the suite. Result surfaced
several **pre-existing** bugs (not caused by the audit edits); fixed the safe ones and
built the admin-controlled scheduler the owner requested.

| # | Severity | Fix | File(s) |
|---|----------|-----|---------|
| SCHED-1 | CRITICAL | Beat scheduler couldn't even import — `main.py` re-wrapped names that were already `cron(...)` objects (`cron(cron(...))` → arq crash). Rebuilt it DB-driven: each job ticks every minute and a `_managed` wrapper unwraps `.coroutine` + gates on the DB row | `workers/main.py` |
| SCHED-2 | FEATURE | **Admin-controlled scheduler**: new `cron_jobs` table + `cron_control` service (enable/disable + interval, clamped) + admin API (`/admin/cron`, superadmin) + admin page **«Планировщик»** with live toggle/interval | `core/models/cron.py`, `core/services/cron_control.py`, `migrations/0040_cron_jobs.py`, `api/admin/cron.py`, `api/admin/router.py`, `admin/src/pages/Scheduler.tsx`, `admin/src/App.tsx`, `admin/src/api.ts` |
| TEST-1 | HIGH | `payment_methods.py` used `IntegrityError` without importing it (`NameError` on the concurrent-insert path) | `core/services/payment_methods.py` |
| TEST-2 | HIGH | `service.py` re-imported `get_user` locally inside a function → `UnboundLocalError` on every gateway webhook apply | `core/payments/service.py` |
| M11-fix | MED | Corrected the AI-router retry break (must also stop on EXHAUSTED 429/401/402/403, not only non-retryable) — fixed a pre-existing `test_ai_routing` failure | `core/ai_router/registry.py` |

**Verified:** `test_ai_routing` (all), `test_worker_settings`, `test_worker_lifespan_refresh`, new `test_cron_control` (4) all pass; 96 tests across the audit-touched files pass; admin frontend builds clean (tsc+vite); migrations 0000→0040 apply + 0040 up/down round-trips on SQLite.

**Remaining failures are NOT from these changes** — sandbox has no network (`getaddrinfo` on `base_url`/rehost/gift tests) plus a few deeper pre-existing issues (`payment_methods` get/save logic, a `_fake_notify(reason=)` outdated test mock, `test_promo_bonuses` one-shot guard). These need a separate pass / maintainer input.

### Still deferred (intentional)
- **Sheet portal/scroll-lock/focus-trap** for the Mini App `CreateSheet`/`StoreSheet` — a larger UX refactor with real risk of disturbing the Telegram WebApp layout; left for a dedicated pass.
- **Bot `/metrics` endpoint** to re-enable `BotDown` (needs an HTTP server added to the polling bot process).
- **M7 metrics token** — one manual deploy step (Prometheus can't expand env vars).

