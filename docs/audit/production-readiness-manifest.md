# CHATGPTFLASHBOT — Production-Readiness Manifest

> Complete file inventory for the zero-trust audit at commit `a93f049`.
> Status legend: `pending` (not yet reviewed) · `reviewed` (read fully, no
> change needed) · `fixed` (defect found + fixed, see commit) · `n/a`
> (vendored/generated/data — out of audit scope). Evidence = test/commit/flow.

**Total tracked files:** 583. Excluded from review scope: `.git`,
`node_modules`, `.venv`, `dist`, `build`, `coverage`, `__pycache__`, tool
caches, binary media, runtime logs (none of these are git-tracked here).

## Summary by area

| Area | Files | Reviewed | Fixed | n/a | Pending |
|---|--:|--:|--:|--:|--:|
| `core` | 111 | 0 | 0 | 0 | 111 |
| `api` | 38 | 0 | 0 | 0 | 38 |
| `bot` | 44 | 0 | 0 | 0 | 44 |
| `workers` | 16 | 0 | 0 | 0 | 16 |
| `migrations` | 46 | 0 | 0 | 0 | 46 |
| `miniapp` | 43 | 0 | 0 | 0 | 43 |
| `admin` | 57 | 0 | 0 | 0 | 57 |
| `tests` | 150 | 0 | 0 | 0 | 150 |
| `loadtests` | 3 | 0 | 0 | 0 | 3 |
| `scripts` | 20 | 0 | 0 | 0 | 20 |
| `monitoring` | 8 | 0 | 0 | 0 | 8 |
| `docs` | 17 | 0 | 0 | 0 | 17 |
| `.github` | 3 | 0 | 0 | 0 | 3 |
| `(root)` | 27 | 0 | 0 | 0 | 27 |
| **TOTAL** | **583** | **0** | **0** | **0** | **583** |

## `core` (111 files)

| File | Status | Purpose / evidence |
|---|---|---|
| `core/__init__.py` | pending | — |
| `core/ai_router/__init__.py` | pending | — |
| `core/ai_router/anthropic_adapter.py` | pending | — |
| `core/ai_router/base.py` | pending | — |
| `core/ai_router/gateways.py` | pending | — |
| `core/ai_router/google_adapter.py` | pending | — |
| `core/ai_router/image_adapters.py` | pending | — |
| `core/ai_router/image_specs.py` | pending | — |
| `core/ai_router/music_adapters.py` | pending | — |
| `core/ai_router/openai_adapter.py` | pending | — |
| `core/ai_router/perplexity_adapter.py` | pending | — |
| `core/ai_router/registry.py` | fixed | fixed `cfdcb0e` — G-1 pass cost_micros to mark_success |
| `core/ai_router/search_adapter.py` | pending | — |
| `core/ai_router/stt_adapter.py` | pending | — |
| `core/ai_router/tts_adapter.py` | pending | — |
| `core/ai_router/video_adapters.py` | pending | — |
| `core/ai_router/video_specs.py` | pending | — |
| `core/ai_router/vision.py` | pending | — |
| `core/bot_client.py` | pending | — |
| `core/config.py` | fixed | fixed — P-1 boot guard for Stripe webhook secret (e03e500) |
| `core/constants.py` | pending | — |
| `core/db.py` | reviewed | reviewed — engine/pool/PgBouncer config correct |
| `core/i18n/__init__.py` | pending | — |
| `core/i18n/locales/__init__.py` | pending | — |
| `core/i18n/locales/ar.py` | pending | — |
| `core/i18n/locales/en.py` | pending | — |
| `core/i18n/locales/es.py` | pending | — |
| `core/i18n/locales/fr.py` | pending | — |
| `core/i18n/locales/pt.py` | pending | — |
| `core/i18n/locales/ru.py` | pending | — |
| `core/i18n/locales/uz.py` | pending | — |
| `core/i18n/locales/zh.py` | pending | — |
| `core/lifecycle.py` | pending | — |
| `core/logging_setup.py` | pending | — |
| `core/models/__init__.py` | pending | — |
| `core/models/admin.py` | fixed | fixed `0de8cd3` — B-2 declare backup_codes_hashed (drift) |
| `core/models/ai_routing.py` | pending | — |
| `core/models/base.py` | pending | — |
| `core/models/billing.py` | pending | — |
| `core/models/bot_instance.py` | pending | — |
| `core/models/catalog.py` | pending | — |
| `core/models/channel_post.py` | pending | — |
| `core/models/contest.py` | pending | — |
| `core/models/crm.py` | pending | — |
| `core/models/cron.py` | pending | — |
| `core/models/feedback.py` | pending | — |
| `core/models/gallery.py` | pending | — |
| `core/models/gift.py` | pending | — |
| `core/models/support.py` | pending | — |
| `core/models/types.py` | pending | — |
| `core/models/user.py` | pending | — |
| `core/payments/__init__.py` | pending | — |
| `core/payments/base.py` | pending | — |
| `core/payments/crypto_gw.py` | pending | — |
| `core/payments/service.py` | pending | — |
| `core/payments/stripe_gw.py` | fixed | fixed — P-1 forged-webhook guard (e03e500) |
| `core/payments/tribute_gw.py` | pending | — |
| `core/payments/yookassa_gw.py` | pending | — |
| `core/queue.py` | pending | — |
| `core/redis_client.py` | pending | — |
| `core/services/__init__.py` | pending | — |
| `core/services/admin_auth.py` | pending | — |
| `core/services/ads.py` | pending | — |
| `core/services/ai_routing.py` | reviewed | reviewed — G-1 spend-cap accrual verified |
| `core/services/analytics.py` | pending | — |
| `core/services/autorenew.py` | fixed | fixed — P-2/P-4 rollback-greenlet + batch (122dc7b) |
| `core/services/billing.py` | fixed | fixed — P-3 _record_tx savepoint (642c33e) |
| `core/services/bots.py` | pending | — |
| `core/services/channel_posts.py` | pending | — |
| `core/services/checkout.py` | pending | — |
| `core/services/contests.py` | pending | — |
| `core/services/context.py` | pending | — |
| `core/services/credits.py` | pending | — |
| `core/services/cron_control.py` | fixed | fixed `2d1c729` — G-4 claim under SELECT FOR UPDATE |
| `core/services/crypto.py` | pending | — |
| `core/services/daily_bonus.py` | pending | — |
| `core/services/documents.py` | pending | — |
| `core/services/feature_flags.py` | pending | — |
| `core/services/feedback.py` | pending | — |
| `core/services/gallery.py` | pending | — |
| `core/services/gate.py` | pending | — |
| `core/services/gateway_keys.py` | pending | — |
| `core/services/gdpr.py` | fixed | fixed — P6 Art.17 erasure deletes stored objects (70343a3) |
| `core/services/gen_notify.py` | pending | — |
| `core/services/gifts.py` | pending | — |
| `core/services/i18n_overrides.py` | pending | — |
| `core/services/i18n_translate.py` | pending | — |
| `core/services/loyalty.py` | pending | — |
| `core/services/media_dispatch.py` | fixed | fixed `cfdcb0e` — G-1 accrue routed model cost |
| `core/services/moderation.py` | pending | — |
| `core/services/notifications.py` | pending | — |
| `core/services/notify.py` | pending | — |
| `core/services/packs.py` | pending | — |
| `core/services/payment_methods.py` | pending | — |
| `core/services/phototools.py` | pending | — |
| `core/services/pricing.py` | pending | — |
| `core/services/promos.py` | pending | — |
| `core/services/provider_keys.py` | pending | — |
| `core/services/providers_admin.py` | pending | — |
| `core/services/quota.py` | pending | — |
| `core/services/ratelimit.py` | fixed | fixed — A-1 peek/incr/reset helpers (06961a7) |
| `core/services/referrals.py` | fixed | fixed — P-3 _grant_once savepoint (642c33e) |
| `core/services/refunds.py` | fixed | fixed — G-2 refund re-check under lock (0084556) |
| `core/services/reports.py` | pending | — |
| `core/services/retention.py` | pending | — |
| `core/services/service_config.py` | pending | — |
| `core/services/storage.py` | fixed | fixed — P6 rehost_remote streaming size cap / OOM guard (2e7bf65) |
| `core/services/support.py` | pending | — |
| `core/services/throttle_config.py` | pending | — |
| `core/services/users.py` | pending | — |
| `core/timeutils.py` | pending | — |

## `api` (38 files)

| File | Status | Purpose / evidence |
|---|---|---|
| `api/__init__.py` | pending | — |
| `api/admin/__init__.py` | pending | — |
| `api/admin/admins.py` | pending | — |
| `api/admin/ai_routing.py` | pending | — |
| `api/admin/analytics.py` | pending | — |
| `api/admin/attention.py` | pending | — |
| `api/admin/audit.py` | pending | — |
| `api/admin/auth.py` | fixed | fixed — A-1 per-account login lockout (06961a7) |
| `api/admin/banners.py` | pending | — |
| `api/admin/bots.py` | pending | — |
| `api/admin/business.py` | pending | — |
| `api/admin/channel.py` | pending | — |
| `api/admin/contests.py` | pending | — |
| `api/admin/crm.py` | pending | — |
| `api/admin/cron.py` | pending | — |
| `api/admin/deps.py` | pending | — |
| `api/admin/effects.py` | pending | — |
| `api/admin/exports.py` | pending | — |
| `api/admin/feedback.py` | pending | — |
| `api/admin/gallery.py` | pending | — |
| `api/admin/health.py` | pending | — |
| `api/admin/localization.py` | pending | — |
| `api/admin/maintenance.py` | pending | — |
| `api/admin/messaging.py` | pending | — |
| `api/admin/ops.py` | pending | — |
| `api/admin/router.py` | pending | — |
| `api/admin/traffic.py` | pending | — |
| `api/admin/users.py` | pending | — |
| `api/carousel.py` | pending | — |
| `api/deps.py` | pending | — |
| `api/images.py` | fixed | fixed — P6 decompression-bomb dimension ceiling (ed1c87e) |
| `api/main.py` | pending | — |
| `api/routers/__init__.py` | pending | — |
| `api/routers/gallery.py` | fixed | fixed — P6 F1 submit rate-limit + F3 image ownership (9545cde, 1cca61a) |
| `api/routers/health.py` | fixed | fixed — A-2 /metrics fail-closed (31c17d5) + P6 F2 Authorization: Bearer (2e0f8ff) |
| `api/routers/miniapp.py` | fixed | fixed — P4 U-3 effect dedup + P7 free_model dedup symmetry (de99766, d3e2b7b) |
| `api/routers/redirect.py` | pending | — |
| `api/routers/webhooks.py` | pending | — |

## `bot` (44 files)

| File | Status | Purpose / evidence |
|---|---|---|
| `bot/__init__.py` | pending | — |
| `bot/format_md.py` | pending | — |
| `bot/handlers/__init__.py` | pending | — |
| `bot/handlers/account.py` | pending | — |
| `bot/handlers/bonus.py` | pending | — |
| `bot/handlers/chat.py` | fixed | fixed — P6 voice TTS first_seen import ImportError (403e894) |
| `bot/handlers/contests.py` | pending | — |
| `bot/handlers/context.py` | pending | — |
| `bot/handlers/documents.py` | pending | — |
| `bot/handlers/gift.py` | pending | — |
| `bot/handlers/groups.py` | pending | — |
| `bot/handlers/inline.py` | pending | — |
| `bot/handlers/invite.py` | pending | — |
| `bot/handlers/kling.py` | pending | — |
| `bot/handlers/links.py` | pending | — |
| `bot/handlers/menus.py` | pending | — |
| `bot/handlers/misc.py` | pending | — |
| `bot/handlers/model.py` | pending | — |
| `bot/handlers/music_gen.py` | pending | — |
| `bot/handlers/packs_buy.py` | pending | — |
| `bot/handlers/photo.py` | pending | — |
| `bot/handlers/premium.py` | pending | — |
| `bot/handlers/promo.py` | pending | — |
| `bot/handlers/roles.py` | pending | — |
| `bot/handlers/search.py` | pending | — |
| `bot/handlers/settings.py` | pending | — |
| `bot/handlers/start.py` | pending | — |
| `bot/handlers/support.py` | pending | — |
| `bot/handlers/video.py` | pending | — |
| `bot/keyboards/__init__.py` | pending | — |
| `bot/keyboards/inline.py` | pending | — |
| `bot/keyboards/menus.py` | pending | — |
| `bot/keyboards/photo_config.py` | pending | — |
| `bot/keyboards/reply.py` | pending | — |
| `bot/keyboards/video_config.py` | pending | — |
| `bot/main.py` | pending | — |
| `bot/middlewares/__init__.py` | pending | — |
| `bot/middlewares/ban.py` | fixed | fixed — P6 successful_payment carve-out (3d0c0cc) |
| `bot/middlewares/core.py` | pending | — |
| `bot/middlewares/gate.py` | fixed | fixed — P6 successful_payment carve-out (3d0c0cc) |
| `bot/middlewares/maintenance.py` | fixed | fixed — P6 successful_payment carve-out (3d0c0cc) |
| `bot/middlewares/throttle.py` | pending | — |
| `bot/states/__init__.py` | pending | — |
| `bot/states/states.py` | pending | — |

## `workers` (16 files)

| File | Status | Purpose / evidence |
|---|---|---|
| `workers/__init__.py` | pending | — |
| `workers/autorenew_tasks.py` | pending | — |
| `workers/avatar_tasks.py` | fixed | fixed `3381928` — G-2 atomic pending→processing claim |
| `workers/billing_tasks.py` | pending | — |
| `workers/broadcast_tasks.py` | pending | — |
| `workers/channel_tasks.py` | pending | — |
| `workers/gen_notify_tasks.py` | pending | — |
| `workers/main.py` | pending | — |
| `workers/music_tasks.py` | fixed | fixed `5296dd3` — G-3 resumable processing-claim |
| `workers/notify_tasks.py` | pending | — |
| `workers/photo_tools_tasks.py` | fixed | fixed `5296dd3` — G-5 conditional claim + import tidy |
| `workers/photoeffect_tasks.py` | pending | — |
| `workers/report_tasks.py` | pending | — |
| `workers/retention_extra_tasks.py` | pending | — |
| `workers/retention_tasks.py` | pending | — |
| `workers/video_tasks.py` | fixed | fixed `5296dd3` — G-3 resumable processing-claim |

## `migrations` (46 files)

| File | Status | Purpose / evidence |
|---|---|---|
| `migrations/env.py` | pending | — |
| `migrations/script.py.mako` | pending | — |
| `migrations/versions/.gitkeep` | pending | — |
| `migrations/versions/0000_baseline.py` | pending | — |
| `migrations/versions/0001_ai_routing.py` | pending | — |
| `migrations/versions/0002_effect_presets.py` | pending | — |
| `migrations/versions/0003_routing_multimodal.py` | pending | — |
| `migrations/versions/0004_user_indexes.py` | pending | — |
| `migrations/versions/0005_rename_diamonds_to_credits.py` | pending | — |
| `migrations/versions/0006_admin_controls.py` | pending | — |
| `migrations/versions/0007_search_job_indexes.py` | pending | — |
| `migrations/versions/0008_daily_bonus.py` | pending | — |
| `migrations/versions/0009_gifts_feedback_crm.py` | pending | — |
| `migrations/versions/0010_support_gallery.py` | pending | — |
| `migrations/versions/0011_user_source.py` | pending | — |
| `migrations/versions/0012_contests_channel.py` | pending | — |
| `migrations/versions/0013_agent_program.py` | pending | — |
| `migrations/versions/0014_user_auto_renew.py` | pending | — |
| `migrations/versions/0015_multibot.py` | pending | — |
| `migrations/versions/0016_payment_methods.py` | pending | — |
| `migrations/versions/0017_account_weight.py` | pending | — |
| `migrations/versions/0018_account_latency.py` | pending | — |
| `migrations/versions/0019_routing_spend.py` | pending | — |
| `migrations/versions/0020_account_spend_limit.py` | pending | — |
| `migrations/versions/0021_audit_created_at_index.py` | pending | — |
| `migrations/versions/0022_widen_user_id_bigint.py` | pending | — |
| `migrations/versions/0023_analytics_window_indexes.py` | pending | — |
| `migrations/versions/0024_genjob_refunded_at.py` | pending | — |
| `migrations/versions/0025_banner_engagement_counters.py` | pending | — |
| `migrations/versions/0026_custom_button_stats.py` | pending | — |
| `migrations/versions/0027_ai_model_token_pricing.py` | pending | — |
| `migrations/versions/0028_banner_locale.py` | pending | — |
| `migrations/versions/0029_effect_prompt_mode.py` | pending | — |
| `migrations/versions/0030_sponsored_effects.py` | pending | — |
| `migrations/versions/0031_contest_prize.py` | pending | — |
| `migrations/versions/0032_drop_agent_program.py` | pending | — |
| `migrations/versions/0033_promo_new_user_gate.py` | pending | — |
| `migrations/versions/0034_user_discount_code.py` | pending | — |
| `migrations/versions/0035_user_ad_reply_count.py` | pending | — |
| `migrations/versions/0036_checkout_intents.py` | pending | — |
| `migrations/versions/0037_round5_schema_fixes.py` | pending | — |
| `migrations/versions/0038_user_cascade_delete.py` | pending | — |
| `migrations/versions/0039_admin_backup_codes.py` | reviewed | reviewed — B-2 root; migration correct, model aligned |
| `migrations/versions/0040_cron_jobs.py` | pending | — |
| `migrations/versions/0041_paymethod_checkout_cascade.py` | pending | — |
| `migrations/versions/0042_search_model.py` | pending | — |

## `miniapp` (43 files)

| File | Status | Purpose / evidence |
|---|---|---|
| `miniapp/e2e/smoke.spec.ts` | pending | — |
| `miniapp/index.html` | pending | — |
| `miniapp/package-lock.json` | pending | — |
| `miniapp/package.json` | pending | — |
| `miniapp/playwright.config.ts` | pending | — |
| `miniapp/src/App.tsx` | pending | — |
| `miniapp/src/__tests__/api-client.test.ts` | pending | — |
| `miniapp/src/__tests__/effectGrid.test.tsx` | pending | — |
| `miniapp/src/__tests__/errorBoundary.test.tsx` | pending | — |
| `miniapp/src/__tests__/i18n.test.ts` | pending | — |
| `miniapp/src/api/client.ts` | fixed | fixed — P7 U-3 idempotency token + U-7 error taxonomy (d3e2b7b, de099d1) |
| `miniapp/src/components/BonusReferral.tsx` | pending | — |
| `miniapp/src/components/Carousel.tsx` | pending | — |
| `miniapp/src/components/CreateSheet.tsx` | fixed | fixed — P7 U-3 synchronous double-submit guard (d3e2b7b) |
| `miniapp/src/components/EffectCard.tsx` | pending | — |
| `miniapp/src/components/EffectGrid.tsx` | pending | — |
| `miniapp/src/components/ErrorBoundary.tsx` | pending | — |
| `miniapp/src/components/Icons.tsx` | pending | — |
| `miniapp/src/components/create/ElementsPanel.tsx` | pending | — |
| `miniapp/src/components/create/GenerateBar.tsx` | pending | — |
| `miniapp/src/components/create/ModeSwitch.tsx` | pending | — |
| `miniapp/src/components/create/ModelPicker.tsx` | pending | — |
| `miniapp/src/components/create/PresetPicker.tsx` | pending | — |
| `miniapp/src/components/create/PromptSection.tsx` | pending | — |
| `miniapp/src/components/create/SettingsPanel.tsx` | pending | — |
| `miniapp/src/components/create/UploadSection.tsx` | pending | — |
| `miniapp/src/components/create/elements.ts` | pending | — |
| `miniapp/src/components/create/templates.ts` | pending | — |
| `miniapp/src/i18n.ts` | pending | — |
| `miniapp/src/main.tsx` | pending | — |
| `miniapp/src/pages/Create.tsx` | fixed | fixed — P7 U-3 synchronous double-submit guard (d3e2b7b) |
| `miniapp/src/pages/History.tsx` | pending | — |
| `miniapp/src/pages/Home.tsx` | pending | — |
| `miniapp/src/pages/Profile.tsx` | pending | — |
| `miniapp/src/pages/Trends.tsx` | pending | — |
| `miniapp/src/poster.ts` | pending | — |
| `miniapp/src/styles.css` | pending | — |
| `miniapp/src/test/setup.ts` | pending | — |
| `miniapp/src/theme.ts` | pending | — |
| `miniapp/src/vite-env.d.ts` | pending | — |
| `miniapp/tsconfig.json` | pending | — |
| `miniapp/vite.config.ts` | pending | — |
| `miniapp/vitest.config.ts` | pending | — |

## `admin` (57 files)

| File | Status | Purpose / evidence |
|---|---|---|
| `admin/README.md` | pending | — |
| `admin/index.html` | pending | — |
| `admin/package-lock.json` | pending | — |
| `admin/package.json` | pending | — |
| `admin/src/App.tsx` | fixed | fixed — U-4 RoleGuard fail-closed default (88eac6b) |
| `admin/src/__tests__/api.test.ts` | pending | — |
| `admin/src/__tests__/dashboard.test.tsx` | pending | — |
| `admin/src/__tests__/errorBoundary.test.tsx` | pending | — |
| `admin/src/__tests__/latestGuard.test.ts` | pending | — |
| `admin/src/__tests__/login.test.tsx` | pending | — |
| `admin/src/__tests__/telegramHtml.test.ts` | pending | — |
| `admin/src/api.ts` | pending | — |
| `admin/src/components/CommandPalette.tsx` | pending | — |
| `admin/src/components/DateField.tsx` | pending | — |
| `admin/src/components/ErrorBoundary.tsx` | pending | — |
| `admin/src/components/Modal.tsx` | pending | — |
| `admin/src/components/Select.tsx` | pending | — |
| `admin/src/components/Switch.tsx` | pending | — |
| `admin/src/lib/countries.ts` | pending | — |
| `admin/src/lib/languages.ts` | pending | — |
| `admin/src/lib/latestGuard.ts` | pending | — |
| `admin/src/lib/telegramHtml.ts` | pending | — |
| `admin/src/main.tsx` | pending | — |
| `admin/src/pages/AIRouting.tsx` | pending | — |
| `admin/src/pages/Admins.tsx` | pending | — |
| `admin/src/pages/Analytics.tsx` | pending | — |
| `admin/src/pages/ApiKeys.tsx` | pending | — |
| `admin/src/pages/Audit.tsx` | pending | — |
| `admin/src/pages/Banners.tsx` | pending | — |
| `admin/src/pages/Bots.tsx` | pending | — |
| `admin/src/pages/Broadcasts.tsx` | pending | — |
| `admin/src/pages/ChannelPosts.tsx` | pending | — |
| `admin/src/pages/Contests.tsx` | pending | — |
| `admin/src/pages/CustomButtons.tsx` | pending | — |
| `admin/src/pages/Dashboard.tsx` | pending | — |
| `admin/src/pages/Effects.tsx` | pending | — |
| `admin/src/pages/Features.tsx` | pending | — |
| `admin/src/pages/Feedback.tsx` | pending | — |
| `admin/src/pages/Gallery.tsx` | pending | — |
| `admin/src/pages/Health.tsx` | pending | — |
| `admin/src/pages/Localization.tsx` | pending | — |
| `admin/src/pages/Login.tsx` | pending | — |
| `admin/src/pages/Maintenance.tsx` | pending | — |
| `admin/src/pages/Payments.tsx` | pending | — |
| `admin/src/pages/Pricing.tsx` | pending | — |
| `admin/src/pages/Promos.tsx` | pending | — |
| `admin/src/pages/Providers.tsx` | pending | — |
| `admin/src/pages/Referrals.tsx` | pending | — |
| `admin/src/pages/Scheduler.tsx` | pending | — |
| `admin/src/pages/Security.tsx` | pending | — |
| `admin/src/pages/Users.tsx` | pending | — |
| `admin/src/styles.css` | pending | — |
| `admin/src/test/setup.ts` | pending | — |
| `admin/src/vite-env.d.ts` | pending | — |
| `admin/tsconfig.json` | pending | — |
| `admin/vite.config.ts` | pending | — |
| `admin/vitest.config.ts` | pending | — |

## `tests` (150 files)

| File | Status | Purpose / evidence |
|---|---|---|
| `tests/__init__.py` | pending | — |
| `tests/conftest.py` | pending | — |
| `tests/test_account_role.py` | pending | — |
| `tests/test_admin.py` | pending | — |
| `tests/test_admin_login_ratelimit.py` | pending | — |
| `tests/test_admin_maintenance.py` | pending | — |
| `tests/test_admins.py` | pending | — |
| `tests/test_admins_admin.py` | pending | — |
| `tests/test_ads.py` | pending | — |
| `tests/test_ai_routing.py` | pending | — |
| `tests/test_ai_routing_admin.py` | pending | — |
| `tests/test_ai_timeouts.py` | pending | — |
| `tests/test_analytics.py` | pending | — |
| `tests/test_analytics_admin.py` | pending | — |
| `tests/test_analytics_indexes.py` | pending | — |
| `tests/test_api_lifespan_refresh.py` | pending | — |
| `tests/test_attention.py` | pending | — |
| `tests/test_audit_admin.py` | pending | — |
| `tests/test_audit_filters.py` | pending | — |
| `tests/test_audit_fixes.py` | pending | — |
| `tests/test_autorenew.py` | pending | — |
| `tests/test_banners_admin.py` | pending | — |
| `tests/test_bot_error_handler.py` | pending | — |
| `tests/test_bot_lifespan_refresh.py` | pending | — |
| `tests/test_bots_admin.py` | pending | — |
| `tests/test_broadcast_admin.py` | pending | — |
| `tests/test_broadcast_segments.py` | pending | — |
| `tests/test_business_admin.py` | pending | — |
| `tests/test_catalog_localized_name.py` | pending | — |
| `tests/test_channel_posts.py` | pending | — |
| `tests/test_chat_streaming.py` | pending | — |
| `tests/test_checkout_intents.py` | pending | — |
| `tests/test_config_keyboard_rows.py` | pending | — |
| `tests/test_contest_prize.py` | pending | — |
| `tests/test_contests.py` | pending | — |
| `tests/test_contests_admin.py` | pending | — |
| `tests/test_context_window.py` | pending | — |
| `tests/test_cors_credentials.py` | pending | — |
| `tests/test_crm.py` | pending | — |
| `tests/test_cron_control.py` | pending | — |
| `tests/test_custom_buttons.py` | pending | — |
| `tests/test_daily_bonus.py` | pending | — |
| `tests/test_dashboard_admin.py` | pending | — |
| `tests/test_doc_links.py` | pending | — |
| `tests/test_document_service.py` | pending | — |
| `tests/test_documents.py` | pending | — |
| `tests/test_documents_escape.py` | pending | — |
| `tests/test_effects.py` | pending | — |
| `tests/test_expire_subscriptions.py` | pending | — |
| `tests/test_exports.py` | pending | — |
| `tests/test_features.py` | pending | — |
| `tests/test_features_admin.py` | pending | — |
| `tests/test_feedback.py` | pending | — |
| `tests/test_feedback_resolve.py` | pending | — |
| `tests/test_fiat_display.py` | pending | — |
| `tests/test_format_md.py` | pending | — |
| `tests/test_free_model.py` | pending | — |
| `tests/test_gallery.py` | pending | — |
| `tests/test_gateway_keys.py` | pending | — |
| `tests/test_gateway_webhooks.py` | pending | — |
| `tests/test_gateways.py` | pending | — |
| `tests/test_gen_notify.py` | pending | — |
| `tests/test_gifts.py` | pending | — |
| `tests/test_groups.py` | pending | — |
| `tests/test_health_ops.py` | pending | — |
| `tests/test_i18n.py` | pending | — |
| `tests/test_images.py` | pending | — |
| `tests/test_inline.py` | pending | — |
| `tests/test_integration.py` | pending | — |
| `tests/test_invite.py` | pending | — |
| `tests/test_localization.py` | pending | — |
| `tests/test_localization_admin.py` | pending | — |
| `tests/test_localization_override_safety.py` | pending | — |
| `tests/test_logging_setup.py` | pending | — |
| `tests/test_login_audit.py` | pending | — |
| `tests/test_loyalty.py` | pending | — |
| `tests/test_maintenance.py` | pending | — |
| `tests/test_maintenance_admin.py` | pending | — |
| `tests/test_media_dispatch.py` | pending | — |
| `tests/test_mfa.py` | pending | — |
| `tests/test_miniapp.py` | pending | — |
| `tests/test_miniapp_charge_atomicity.py` | pending | — |
| `tests/test_miniapp_history.py` | pending | — |
| `tests/test_miniapp_offers.py` | pending | — |
| `tests/test_miniapp_promo_endpoint.py` | pending | — |
| `tests/test_miniapp_prompt_mode.py` | pending | — |
| `tests/test_miniapp_sections.py` | pending | — |
| `tests/test_mock_ai_server.py` | pending | — |
| `tests/test_model_badge.py` | pending | — |
| `tests/test_moderation.py` | pending | — |
| `tests/test_multibot.py` | pending | — |
| `tests/test_notify.py` | pending | — |
| `tests/test_openrouter_gateway.py` | pending | — |
| `tests/test_payment_apply_event.py` | pending | — |
| `tests/test_payment_methods.py` | pending | — |
| `tests/test_payment_routing.py` | pending | — |
| `tests/test_payments.py` | pending | — |
| `tests/test_payments_admin.py` | pending | — |
| `tests/test_photo_edit_chat.py` | pending | — |
| `tests/test_photo_variants.py` | pending | — |
| `tests/test_phototool_pricing.py` | pending | — |
| `tests/test_phototools.py` | pending | — |
| `tests/test_pricing_config.py` | pending | — |
| `tests/test_promo_bonuses.py` | pending | — |
| `tests/test_promo_discount.py` | pending | — |
| `tests/test_promo_premium_gate.py` | pending | — |
| `tests/test_promos.py` | pending | — |
| `tests/test_provider_base_url_admin.py` | pending | — |
| `tests/test_provider_keys.py` | pending | — |
| `tests/test_queue_priority.py` | pending | — |
| `tests/test_quota.py` | pending | — |
| `tests/test_referral_fraud.py` | pending | — |
| `tests/test_referral_two_sided.py` | pending | — |
| `tests/test_referrals_admin.py` | pending | — |
| `tests/test_refund_job_idempotent.py` | pending | — |
| `tests/test_refunds_admin.py` | pending | — |
| `tests/test_reports.py` | pending | — |
| `tests/test_result_rehost.py` | pending | — |
| `tests/test_retention.py` | pending | — |
| `tests/test_role_input_routing.py` | pending | — |
| `tests/test_roles.py` | pending | — |
| `tests/test_routing.py` | pending | — |
| `tests/test_sale.py` | pending | — |
| `tests/test_sale_display.py` | pending | — |
| `tests/test_search_routing.py` | pending | — |
| `tests/test_sections.py` | pending | — |
| `tests/test_security_admin.py` | pending | — |
| `tests/test_security_hardening.py` | pending | — |
| `tests/test_service_config.py` | pending | — |
| `tests/test_service_options.py` | pending | — |
| `tests/test_settings_role.py` | pending | — |
| `tests/test_sponsored_effects.py` | pending | — |
| `tests/test_stars_referral_recovery.py` | pending | — |
| `tests/test_support.py` | pending | — |
| `tests/test_traffic.py` | pending | — |
| `tests/test_user_id_column_widths.py` | pending | — |
| `tests/test_user_language.py` | pending | — |
| `tests/test_users_admin.py` | pending | — |
| `tests/test_video.py` | pending | — |
| `tests/test_video_delivery_origin.py` | pending | — |
| `tests/test_voice_input.py` | pending | — |
| `tests/test_voice_output.py` | pending | — |
| `tests/test_webapp_auth.py` | pending | — |
| `tests/test_webhook_idempotency.py` | pending | — |
| `tests/test_wiring.py` | pending | — |
| `tests/test_worker_idempotency.py` | pending | — |
| `tests/test_worker_lifespan_refresh.py` | pending | — |
| `tests/test_worker_refunds.py` | pending | — |
| `tests/test_worker_settings.py` | pending | — |
| `tests/test_yookassa_receipt.py` | pending | — |

## `loadtests` (3 files)

| File | Status | Purpose / evidence |
|---|---|---|
| `loadtests/README.md` | pending | — |
| `loadtests/k6/api.js` | pending | — |
| `loadtests/locust/locustfile.py` | pending | — |

## `scripts` (20 files)

| File | Status | Purpose / evidence |
|---|---|---|
| `scripts/__init__.py` | pending | — |
| `scripts/backfill_country.py` | pending | — |
| `scripts/backup.sh` | pending | — |
| `scripts/check_migrations.py` | pending | — |
| `scripts/create_admin.py` | pending | — |
| `scripts/db_maintenance.sql` | pending | — |
| `scripts/gateway_check.py` | pending | — |
| `scripts/init_db.py` | pending | — |
| `scripts/live_check.py` | pending | — |
| `scripts/lock-deps.sh` | pending | — |
| `scripts/mock_ai_server.py` | pending | — |
| `scripts/restore.sh` | pending | — |
| `scripts/restore_test.sh` | pending | — |
| `scripts/run_loadtests.sh` | pending | — |
| `scripts/seed_ai_models.py` | pending | — |
| `scripts/seed_catalogs.py` | pending | — |
| `scripts/share.ps1` | pending | — |
| `scripts/smoke_test.sh` | pending | — |
| `scripts/start_all.ps1` | pending | — |
| `scripts/start_workers.ps1` | pending | — |

## `monitoring` (8 files)

| File | Status | Purpose / evidence |
|---|---|---|
| `monitoring/alertmanager.yml` | pending | — |
| `monitoring/alerts.yml` | pending | — |
| `monitoring/grafana/dashboards/aibot.json` | pending | — |
| `monitoring/grafana/provisioning/dashboards/dashboards.yml` | pending | — |
| `monitoring/grafana/provisioning/datasources/datasources.yml` | pending | — |
| `monitoring/loki-config.yml` | pending | — |
| `monitoring/prometheus.yml` | fixed | fixed — P6 F2 recommend Authorization: Bearer (2e0f8ff) |
| `monitoring/promtail-config.yml` | pending | — |

## `docs` (17 files)

| File | Status | Purpose / evidence |
|---|---|---|
| `docs/API.md` | pending | — |
| `docs/ARCHITECTURE.md` | pending | — |
| `docs/BACKUP.md` | pending | — |
| `docs/CICD.md` | pending | — |
| `docs/DEPLOYMENT.md` | pending | — |
| `docs/ENV.md` | pending | — |
| `docs/MONITORING.md` | pending | — |
| `docs/RESTORE.md` | pending | — |
| `docs/RUNBOOK.md` | pending | — |
| `docs/SECURITY.md` | pending | — |
| `docs/SPEC_RU.md` | pending | — |
| `docs/TROUBLESHOOTING.md` | pending | — |
| `docs/audit/production-readiness-report.md` | pending | — |
| `docs/legal/privacy_ru.md` | pending | — |
| `docs/legal/terms_ru.md` | pending | — |
| `docs/superpowers/specs/2026-06-17-miniapp-higgsfield-presets-design.md` | pending | — |
| `docs/superpowers/specs/2026-06-20-frontend-responsive-refactor-design.md` | pending | — |

## `.github` (3 files)

| File | Status | Purpose / evidence |
|---|---|---|
| `.github/dependabot.yml` | pending | — |
| `.github/workflows/ci.yml` | pending | — |
| `.github/workflows/release.yml` | pending | — |

## `(root)` (27 files)

| File | Status | Purpose / evidence |
|---|---|---|
| `.dockerignore` | pending | — |
| `.env.example` | pending | — |
| `.env.staging.example` | pending | — |
| `.gitignore` | pending | — |
| `AUDIT_REPORT.md` | pending | — |
| `AUDIT_REPORT_2026-07-06.md` | pending | — |
| `BOT_MAP.md` | pending | — |
| `CHANGELOG.md` | pending | — |
| `CLAUDE.md` | pending | — |
| `CONTRIBUTING.md` | pending | — |
| `Caddyfile` | pending | — |
| `DEPLOYMENT.md` | pending | — |
| `DEPLOY_AWS.md` | pending | — |
| `Dockerfile` | pending | — |
| `GRILL_BACKLOG.md` | pending | — |
| `IMPLEMENTATION_PLAN.md` | pending | — |
| `PROJECT_SPEC.md` | pending | — |
| `README.md` | pending | — |
| `RELEASE_CHECKLIST.md` | pending | — |
| `alembic.ini` | pending | — |
| `docker-compose.monitoring.yml` | pending | — |
| `docker-compose.prod.yml` | pending | — |
| `docker-compose.staging.yml` | pending | — |
| `docker-compose.yml` | pending | — |
| `pyproject.toml` | pending | — |
| `requirements-dev.txt` | pending | — |
| `requirements.txt` | pending | — |
