# Staging Smoke-Test Checklist — pre-launch Go/No-Go

> Closes the gap automated tests **cannot** cover: the seams with real external services
> (Telegram, AI providers, payment gateways) and real infra (Postgres/Redis/PgBouncer
> under load). Everything below runs on a **staging** deploy — never first on prod.
>
> How to use: work top-to-bottom, tick each box, and when something fails **stop and log
> it** (don't tick "works"). The final Go/No-Go gate lists the blockers that must be green.
>
> Legend: 🟢 = must pass to launch · 🟡 = should pass · ⏱ = timed/observed.

---

## 0. Pre-flight — bring the stack up

Grounded in `docker-compose.prod.yml` (services: `postgres pgbouncer redis omniroute
minio bot api worker beat caddy backup`).

- [ ] 🟢 `.env` filled with **staging** secrets (never prod keys): `BOT_TOKEN` (a
      dedicated staging bot from @BotFather), provider keys, `STRIPE_SECRET` +
      `STRIPE_WEBHOOK_SECRET`, `YOOKASSA_*`, `SECRET_KEY`, `FERNET_KEY`, DB/Redis creds.
- [ ] 🟢 PgBouncer on: `DB_PGBOUNCER=true` and `DATABASE_URL=…@pgbouncer:6432/…`
      (Runbook R1 in `docs/SCALING.md`).
- [ ] 🟢 `docker compose -f docker-compose.prod.yml up -d` → all services `healthy`
      (`docker compose ps`; no restart loops).
- [ ] 🟢 Migrations applied: `docker compose exec api alembic upgrade head` → "head".
- [ ] 🟢 API health: `curl -fsS https://<staging>/api/health` → 200. `GET /api/metrics`
      returns Prometheus text.
- [ ] 🟢 Webhook registered: bot answers in Telegram (send `/start` — see §1). If polling
      instead of webhook, confirm the bot process is consuming updates.
- [ ] 🟡 MinIO/S3 reachable and the bucket exists (generation results rehost here).

**If a service won't start:** `docker compose logs <svc>` — look for missing env, DB
connection refused (PgBouncer DSN wrong), or Fernet/JWT key errors.

---

## 1. Telegram bot — real client, real provider keys 🟢

Do these as a **normal user** in the staging bot (a second Telegram account, not admin).
Every generation must: deduct credits → show progress → deliver the media → leave a
`generation_jobs` row in `complete`/`delivered`.

- [ ] 🟢 `/start` — welcome message + main menu/keyboard renders; a `users` row is created.
- [ ] 🟢 `/help`, `/settings`, `/language` (switch RU↔EN↔AR — check Arabic renders RTL),
      `/account` — all respond, no tracebacks.
- [ ] 🟢 **Chat** — send a plain text message → streamed/real reply from the live model.
- [ ] 🟢 `/model` — switch model, send again → answer comes from the new model.
- [ ] 🟢 `/photo` — run an image generation → image delivered; try each **aspect ratio /
      size** option the keyboard offers.
- [ ] 🟢 `/video` — run a video → delivered; try each **duration** and **ratio**.
- [ ] 🟢 `/music` — generate a track → audio delivered.
- [ ] 🟢 `/s <query>` (search) — grounded answer with sources returned.
- [ ] 🟢 `/ava` (avatar) — upload a selfie → avatar album delivered.
- [ ] 🟡 `/wow` effects — pick a photo/video effect, upload input → result delivered;
      verify **file type/extension** of the output is correct.
- [ ] 🟢 Voice **in** (send a voice message) → STT transcribes; voice **out** if enabled → TTS audio plays.
- [ ] 🟢 `/cancel` mid-generation → job cancels, **credits refunded** (check balance before/after).
- [ ] 🟡 Insufficient balance → run a generation with too few credits → blocked with a clear
      "top up" prompt, **no** job created, **no** silent debit.
- [ ] 🟢 Moderation gate → send a prompt that must be blocked → refused, no generation, no charge.

### Referral & promo
- [ ] 🟢 `/invite` / `/links` — get a referral link; open it from a **fresh** account →
      `/start` → new user attributed to referrer.
- [ ] 🟢 Referred user makes a **paid** purchase → referrer credited `REFERRAL_REWARD_CREDITS`
      (matches the `money-flow` e2e; confirm it fires on **real** payment).
- [ ] 🟡 `/promo <code>` / `/redeem` / `/gift` / `/bonus` — apply a code created in admin →
      credits granted once; re-applying the same code is rejected.
- [ ] 🟡 `/contests` — join a contest; admin draw (see §3) picks a winner and notifies.

### GDPR / account
- [ ] 🟢 `/export_data` / `/privacy` — user receives their data export.
- [ ] 🟢 `/delete_account` → confirm with `CONFIRM` → account + related rows CASCADE-deleted;
      user can `/start` again as brand-new.
- [ ] 🟡 `/support` / `/report` — creates a support/feedback entry visible in admin (§3).

**Where to look on failure:** `docker compose logs -f bot worker` — a stuck generation is
usually a provider 4xx/timeout (check the `AIAccount` got `mark_exhausted`), a missing
provider key, or the SSRF allowlist rejecting a result URL.

---

## 2. Mini App — real device + Telegram WebApp 🟢

Open the Mini App from the staging bot on a **real phone** (iOS **and** Android if possible)
and once on desktop Telegram. Pages: Home, Create, History, Trends, Profile.

- [ ] 🟢 Launches inside Telegram (initData validates); opening the URL **outside** Telegram
      shows the "Open in Telegram" gate, not a broken app.
- [ ] 🟢 **Home** — banners/carousel load; catalog cards render with thumbnails and price pills.
- [ ] 🟢 **Create** — pick an effect → sheet opens → upload photo(s) → prompt → the
      **Elements** panel opens with a solid background (regression check for the
      `--body`→`--bg` fix) → generate → stepped progress → result hero renders.
- [ ] 🟢 Cost bar shows the right price; low-balance state warns and links to store.
- [ ] 🟢 **History** — past jobs listed with thumbnails; tap opens result; "↻ redo" re-runs.
- [ ] 🟢 **Profile** — credits/stats correct; **buy credits / subscription** CTA opens
      Telegram payment or the checkout link.
- [ ] 🟡 **Trends** — loads without error.
- [ ] 🟡 Safe-area: no content under the notch / home indicator; floating nav not clipped.
- [ ] 🟡 RTL: switch to Arabic → layout mirrors (badges, arrows, close buttons on the right).
- [ ] 🟢 Pull-to-refresh / re-open after a generation → balance and history are **fresh**
      (read-your-write, not a stale cache).

**Where to look:** browser devtools console in Telegram desktop (`Ctrl+Shift+I` on the
WebApp), and `docker compose logs -f api` for 4xx/5xx on `/api/*` calls.

---

## 3. Admin panel — every consolidated page + money actions 🟢

Log in at `https://<staging>/admin/login` as a **superadmin**. The panel is 18 routes;
several are tabbed containers (AISetup, AccessSecurity, PricingPromos, Outreach, SystemOps,
Overview, Content). Click through each once.

- [ ] 🟢 Login works; **MFA/TOTP** challenge if the role requires it; wrong password rejected;
      logout invalidates the session (JWT `token_version`).
- [ ] 🟢 **Overview / Dashboard / Analytics** — metrics load, no NaN/undefined; period switcher
      and custom date range work; revenue split by currency correct.
- [ ] 🟢 **Users** — search, open a user card, deep-link `#id` works; **grant premium** and
      **adjust credits** → change reflected + an **audit-log** row written (atomic).
- [ ] 🟢 **Payments** — a real staging payment appears; **refund** a payment → gateway refund
      fires (idempotent, `refund:{tx}` key) + audit row; balance adjusts.
- [ ] 🟢 **PricingPromos** — edit a base price → the bot/Mini App reflects it (cache invalidates);
      create a promo code → redeemable in §1.
- [ ] 🟢 **AISetup / AIRouting / Providers / ApiKeys** — add an `AIAccount` (key stored
      Fernet-encrypted, `enc::`), toggle a model, watch routing pick it; a 429'd account gets
      sidelined not infinite-retried.
- [ ] 🟢 **Content / Effects / Banners / Gallery** — CRUD an effect and a banner; gallery
      moderation approve/reject works; changes show in the Mini App.
- [ ] 🟢 **Outreach / Broadcasts / ChannelPosts** — send a **test** broadcast to yourself →
      delivered once (no double-send); scheduled post fires at its time.
- [ ] 🟡 **Contests** — draw a winner → single winner, notified, audit row.
- [ ] 🟡 **AccessSecurity / Admins / Audit** — create a lower-role admin; audit timeline shows
      every money/security action; a support-role admin **cannot** see superadmin-only tabs.
- [ ] 🟡 **SystemOps (Maintenance / Scheduler)** — cron list renders; a manual maintenance
      action runs; logs viewer shows output.
- [ ] 🟡 **Localization** — edit a string → reflected in bot/Mini App after cache TTL.
- [ ] 🟡 **Theme** — toggle light/dark (sidebar) → whole panel re-themes, accent tints go
      green in light (regression check for the `--accent-rgb` fix), no unreadable contrast.
- [ ] 🟡 **Mobile** — open admin on a phone → sidebar becomes a top bar; theme + logout reachable.

**Where to look:** `docker compose logs -f api`; a failed money action that left NO audit row
is a 🟢 blocker (the atomic audit-trail is a hard invariant).

---

## 4. Payments — live gateway webhooks 🟢

Use gateway **test mode** first, then one real small-amount transaction per live gateway.
Routes: `/api/webhook/stripe`, `/webhook/yookassa`, `/webhook/crypto`, `/webhook/tribute`.

- [ ] 🟢 **Stripe** — real checkout → `checkout.session.completed` webhook → credits/subscription
      granted **once**; signature verified (a forged/unsigned body is rejected — fail-closed).
- [ ] 🟢 **Stripe idempotency** — gateway retries the same event → **no** double credit.
- [ ] 🟢 **YooKassa** — real payment → webhook re-fetches the payment server-side → granted once.
- [ ] 🟡 **Crypto / Tribute** (if enabled for launch) — one success path each.
- [ ] 🟢 **Refund** from admin (§3) reverses exactly once; user notified if applicable.
- [ ] 🟢 **Amount tamper** — a webhook with a mismatched amount is rejected (matches money-flow e2e).

**Where to look:** gateway dashboard (event delivery + response 200), `logs -f api`, and the
`transactions` table (status transitions, no duplicates).

---

## 5. Load / capacity ⏱ 🟡 (needed for the "millions" claim, not for a soft launch)

Per `docs/SCALING.md` — local tests only prove app-layer efficiency; real capacity needs this.

- [ ] ⏱ Run `loadtests/k6` (or locust) `soak` against staging for ≥15 min at expected peak.
- [ ] 🟢 No `pool_timeout` / "too many connections" errors → PgBouncer is doing its job
      (`SHOW POOLS;` on pgbouncer; app conns collapse to the pool size).
- [ ] 🟡 p95 latency on hot reads (`/profile`, `/jobs`, `/billing/offers`) stays < ~1s under load.
- [ ] 🟡 Worker queue drains — generations don't back up unboundedly; the stuck-job sweep
      recovers an artificially killed worker's job (no double-refund).
- [ ] 🟡 Redis memory stable; no unbounded key growth.

---

## 6. First-hour monitoring (right after cutover) ⏱

- [ ] ⏱ Tail `docker compose logs -f api bot worker` — watch for tracebacks / 5xx spikes.
- [ ] ⏱ `GET /api/metrics` → error rate, latency, queue depth within expected bands.
- [ ] ⏱ One real end-to-end purchase + generation by you, on prod, in the first 10 minutes.
- [ ] ⏱ Postgres connection count stable (PgBouncer); disk/CPU not climbing abnormally.
- [ ] ⏱ Backups running (`backup` service) — verify one snapshot lands.

---

## 7. Rollback plan (decide BEFORE launch)

- [ ] 🟢 Previous image tag known and re-deployable in one command.
- [ ] 🟢 `alembic downgrade -1` rehearsed on staging for the latest migration (or confirmed
      forward-only + safe).
- [ ] 🟢 A "maintenance mode" / bot-disable switch exists to stop new charges if something
      goes wrong mid-incident.

---

## Go / No-Go gate

**GO only if every 🟢 above is ticked.** Specifically, do not launch if any of these is red:

1. A generation charges credits but doesn't deliver (or delivers without charging).
2. A payment double-credits, or a forged/tampered webhook is accepted.
3. A money/security admin action leaves no audit-log row.
4. `/delete_account` doesn't fully delete (GDPR/legal blocker).
5. The bot or API crash-loops, or health is not 200.
6. Under `soak` load, connections exhaust (PgBouncer misconfigured).

🟡 items failing = launch with a known-issues list and a fast-follow, not a hard block —
**your call**, but write them down.

> Automated coverage already green (re-run any time): `pytest -q` (1055),
> `python scripts/e2e_pipeline_check.py` (9/9), `python scripts/money_flow_check.py` (7/7).
> This checklist is the part those cannot prove.
