"""Centralised application configuration (pydantic-settings).

All business numbers live here as defaults but may be overridden at runtime via
the `pricing` DB table (see core.services.pricing). Secrets come from the .env
file / environment only.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Telegram ---
    bot_token: str = ""
    webhook_base_url: str = ""
    # Secret token Telegram echoes back in X-Telegram-Bot-Api-Secret-Token so the
    # webhook endpoint can reject forged updates. Auto-derived if left empty.
    webhook_secret: str = ""
    miniapp_url: str = ""
    admin_user_ids: str = ""
    # Telegram chat id that receives scheduled admin analytics reports (ТЗ §8).
    # 0 = fall back to the first id in admin_user_ids.
    report_chat_id: int = 0
    # Reject Mini App initData older than this (seconds) to stop replay of a
    # leaked initData string. 0 disables the check.
    initdata_max_age: int = 86400

    # --- Run mode ---
    bot_mode: str = "polling"  # polling | webhook
    env: str = "dev"
    # FIX: AUDIT-M4 - explicit public-deploy override. is_public_deploy previously
    # keyed only on bot_mode=="webhook", which ONLY the bot process sets — so the
    # internet-facing API/worker/beat (BOT_MODE=polling) evaluated it as False and
    # skipped the prod-secret / admin-IP / metrics-token / dev-bypass fail-closed
    # guards. Set PUBLIC_DEPLOY=true in prod so every process fails closed.
    public_deploy: bool = False
    # Local-only convenience: when True AND env is dev/test, the Mini App API
    # accepts requests without valid Telegram initData and treats them as a fixed
    # test user. MUST stay False whenever the API is publicly reachable (e.g. via a
    # tunnel) — otherwise anyone can call /api/* unauthenticated. Default OFF.
    dev_webapp_bypass: bool = False
    log_level: str = "INFO"
    # Path to the application log file the admin "view logs" endpoint tails (§8).
    log_file: str = "logs/app.log"
    sentry_dsn: str = ""

    # --- Infra ---
    database_url: str = "postgresql+asyncpg://aiobot:aiobot@localhost:5432/aiobot"
    redis_url: str = "redis://localhost:6379/0"
    # DB connection pool, per process. Total server connections =
    # (db_pool_size + db_max_overflow) × every process (each gunicorn worker, the
    # bot, each arq worker, beat). Keep the product under Postgres max_connections,
    # or front Postgres with PgBouncer and set db_pgbouncer=True (below).
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800  # drop connections older than 30 min (avoids stale)
    # Set True when DATABASE_URL points at PgBouncer in *transaction* pooling mode:
    # the app then keeps NO local pool (NullPool — PgBouncer multiplexes) and
    # disables prepared-statement caches, which are incompatible with txn pooling.
    db_pgbouncer: bool = False
    # A generation job stuck in pending/processing longer than this (minutes) is
    # treated as a crashed worker: the beat sweep fails it and refunds the charge.
    # Keep well above the slowest real generation so a long-running job is never
    # refunded out from under an active worker.
    stuck_job_minutes: int = 30
    s3_endpoint: str = ""
    s3_key: str = ""
    s3_secret: str = ""
    s3_bucket: str = "aiobot"
    s3_public_url: str = ""

    # --- AI providers ---
    openai_api_key: str = ""
    # Explicit OpenAI endpoint + image model. Set explicitly so the openai SDK
    # never silently inherits an ambient OPENAI_BASE_URL from the environment
    # (which could route requests — and the API key — to an unintended proxy).
    openai_base_url: str = "https://api.openai.com/v1"
    openai_image_model: str = "gpt-image-1"
    # Logical text-model key the admin localization editor's "Перевести AI" button
    # routes through (via the AI router, core.ai_router.registry.chat) — so machine
    # translation uses the SAME provider/account the bot's chat uses, with the same
    # fallback, and is never separately configured. Must be a key in constants.TEXT_MODELS.
    localization_translate_model_key: str = "gpt_5_mini"
    # Hard request timeout (seconds) for the SYNCHRONOUS AI SDK calls a user waits
    # on live: text chat / translate, voice TTS+STT, vision. Without it the OpenAI/
    # Anthropic/Google SDKs default to a 600s (10-min) read timeout, so a hung — not
    # errored — upstream would block the chat turn for ten minutes AND defeat the
    # router's fallback/retry (those advance only on a raised error, never on a hang).
    ai_request_timeout: int = 60
    # Longer timeout (seconds) for image generation via the OpenAI/Google SDKs, which
    # legitimately takes longer than a chat turn (matches the 120s the httpx media
    # gateways already use). Still bounded so a stuck image call fails over instead
    # of hanging on the SDK's 600s default.
    ai_image_timeout: int = 120
    openrouter_api_key: str = ""  # OpenAI-compatible gateway (text router fallback)
    # When True, the OpenRouter key is free-tier ($0 balance): EVERY logical model
    # is routed to one free model and the per-model cost multiplier is forced to 1
    # so users are not over-charged for a "top" model they don't actually receive.
    # Set False once the key is funded and real per-model ids are mapped.
    openrouter_free_tier: bool = True
    anthropic_api_key: str = ""
    google_api_key: str = ""
    deepseek_api_key: str = ""
    perplexity_api_key: str = ""
    kling_api_key: str = ""
    kling_secret_key: str = ""  # FIX: H5 - Kling requires JWT from access_key + secret_key
    minimax_api_key: str = ""
    pika_api_key: str = ""
    seedream_api_key: str = ""
    bfl_api_key: str = ""
    midjourney_api_key: str = ""
    suno_api_key: str = ""
    # FIX: SKILL-V1 - suno_base_url was missing from Settings (extra="ignore"
    # silently dropped the env var), so AI-18's `getattr(settings, "suno_base_url", "")`
    # always returned "" and the default api.suno.ai was used. Adding it here
    # makes the env var actually take effect. SSRF validation happens in the
    # adapter at submit() time via _is_ssrf_url_async on the resolved URL.
    suno_base_url: str = ""
    # FIX: AUDIT13-M2 - the model id sent to the Suno aggregator. The UI advertises
    # "Suno V5.5", but the adapter hard-coded "suno-v4", so users paid for V5.5 and got
    # v4. Set SUNO_MODEL to your aggregator's EXACT V5.5 model string so the sent model
    # matches the label. Default keeps the historical value; override it in .env.
    suno_model: str = "suno-v4"
    xai_api_key: str = ""
    replicate_api_key: str = ""  # фото-инструменты §5: face swap / upscale / avatars

    # --- Payments ---
    tribute_api_key: str = ""
    # Tribute's REST/webhook field names are NOT yet confirmed against its docs
    # (see core.payments.tribute_gw). The gateway stays INERT — it neither offers
    # checkouts nor applies webhooks — until an operator who has verified the field
    # mapping against the live API sets this True. Prevents silently accepting (or
    # dropping) СБП payments through an unverified integration.
    tribute_api_verified: bool = False
    yookassa_shop_id: str = ""
    yookassa_secret: str = ""
    # 54-ФЗ fiscal receipts. Master switch: when False the YooKassa payment
    # request carries NO receipt (behaviour unchanged). Turn on only when the
    # merchant is registered under 54-ФЗ and a fiscal data operator is attached.
    yookassa_receipt_enabled: bool = False
    # YooKassa vat_code enum: 1=без НДС, 2=НДС 0%, 3=10%, 4=20%, 5=10/110, 6=20/120.
    yookassa_vat_code: int = 1
    # Optional СНО (tax system) code; sent only when set. None = omit the field.
    yookassa_tax_system_code: int | None = None
    # Fallback receipt customer contact (email or phone) — the gateway has no
    # per-user email at checkout, so a receipt needs this to be deliverable.
    yookassa_receipt_contact: str = ""
    stripe_secret: str = ""
    stripe_webhook_secret: str = ""
    # Crypto payments via @CryptoBot (Crypto Pay API). Token from @CryptoBot →
    # Crypto Pay → Create App. Set testnet=True while testing against @CryptoTestnetBot.
    crypto_pay_token: str = ""
    crypto_pay_testnet: bool = False

    # --- Business config ---
    # Stars -> fiat for external gateways (overridable via pricing table)
    stars_to_rub: float = 1.4
    stars_to_usd: float = 0.014
    # Rolling chat memory: how many recent Q&A pairs the bot keeps as context per
    # user (higher = smarter dialogue, more tokens/cost per request).
    chat_context_pairs: int = 10
    # Anti-flood: max bot actions per user per window (seconds). Overridable at
    # runtime via the `pricing` table keys throttle_limit / throttle_window
    # (admin → Цены), see core.services.throttle_config.
    throttle_limit: int = 20
    throttle_window: int = 10
    free_text_weekly: int = 100
    # Daily login-streak bonus (🪙 credits): reward = base + step*(streak-1), capped.
    daily_bonus_base: int = 5
    daily_bonus_step: int = 1
    daily_bonus_cap: int = 25
    free_miniapp_weekly: int = 25
    premium_daily: int = 100
    premium_x2_daily: int = 200
    gate_channel: str = ""
    support_contact: str = "@lilcipher"
    brand_name: str = "SUPER AI BOT"

    # --- Admin ---
    admin_jwt_secret: str = "change-me-in-prod"
    admin_ip_allowlist: str = ""
    # Roles for which TOTP 2FA is MANDATORY (§8): such an admin without an enrolled
    # secret gets a restricted setup-scoped session that can ONLY enroll 2FA.
    mfa_required_roles: str = "admin,superadmin"
    # If set, GET /metrics requires ?token=... (or X-Metrics-Token header). Leave
    # empty only when /metrics is unreachable from the public internet.
    metrics_token: str = ""
    # FIX: AUDIT-FINAL-14 - removed duplicate `webhook_secret` declaration. The
    # field is already declared at line 24 with the same type + default; having
    # it twice is a code smell and a merge-conflict magnet. The single field at
    # line 24 is the canonical declaration; the `webhook_secret_property`
    # accessor below derives it from BOT_TOKEN when the explicit value is empty.
    # Secret for encrypting stored API keys at rest (falls back to admin_jwt_secret).
    enc_secret: str = ""
    # Optional comma-separated host-suffix allowlist for admin-set AI account
    # base_url values (SSRF defence). Empty = no allowlist, but literal non-public
    # IPs are still rejected. Add internal hosts here (e.g. "omniroute") to permit
    # them. See api.admin.ai_routing._validate_base_url.
    ai_base_url_allowlist: str = ""

    # --- Webhook source restrictions ---
    # CORS origins for the Mini App API (comma-separated). "*" only for dev.
    cors_origins: str = "*"
    # YooKassa has no webhook signature; restrict by its published notification
    # IPs instead (https://yookassa.ru/developers/using-api/webhooks#ip).
    yookassa_webhook_ips: str = (
        "185.71.76.0/27,185.71.77.0/27,77.75.153.0/25,"
        "77.75.156.11,77.75.156.35,77.75.154.128/25,2a02:5180::/32"
    )

    @property
    def is_public_deploy(self) -> bool:
        """True when this deploy is reachable from the public internet. Used to fail
        closed on insecure secrets / anonymous access even if ENV was mistakenly left
        at dev/test. FIX: AUDIT-M4 - covers ALL processes, not just the webhook bot:
        an explicit PUBLIC_DEPLOY flag OR a shared WEBHOOK_BASE_URL (present in every
        process via the same .env) both mark the deploy public. Pure local dev leaves
        both unset → False."""
        return self.public_deploy or bool(self.webhook_base_url)

    def _require_prod_secret(self) -> None:
        """Fail fast on insecure defaults / missing secrets in production — OR
        whenever a public webhook deploy is configured, even if ENV was left at
        dev/test (a forgotten ENV must not ship default secrets to the internet)."""
        if self.env in ("dev", "test") and not self.is_public_deploy:
            return
        if self.admin_jwt_secret == "change-me-in-prod":
            raise RuntimeError(
                "ADMIN_JWT_SECRET is still the default 'change-me-in-prod'. "
                "Set a strong random secret before running in production."
            )
        if not self.enc_secret:
            raise RuntimeError(
                "ENC_SECRET is empty. Set a dedicated secret for encrypting stored "
                "API keys in production — falling back to ADMIN_JWT_SECRET means "
                "rotating the JWT secret would silently corrupt all stored keys."
            )
        if not self.bot_token:
            raise RuntimeError("BOT_TOKEN is required in production.")
        # Object storage: when S3/MinIO is in use, refuse the public-default
        # 'minioadmin' creds — they double as the MinIO root account, so leaving
        # them gives anyone on the docker network full access to user uploads.
        if self.s3_endpoint and (
            self.s3_key == "minioadmin" or self.s3_secret == "minioadmin"
        ):
            raise RuntimeError(
                "S3_KEY/S3_SECRET are still the default 'minioadmin'. These are the "
                "MinIO root credentials — set strong, unique values in production "
                "(password >= 8 chars)."
            )
        # Wildcard CORS in prod is a hard fail, not a warning: the operator must
        # make a conscious choice. The prod stack serves the Mini App same-origin
        # (Caddy), so CORS usually isn't needed — set CORS_ORIGINS to the exact
        # Mini App URL(s), e.g. https://$DOMAIN. (Empty also resolves to '*' here.)
        if "*" in self.cors_origin_list:
            raise RuntimeError(
                "CORS_ORIGINS is '*' (or empty) in production. Set it to the exact "
                "Mini App origin(s), e.g. CORS_ORIGINS=https://your.domain — the "
                "prod stack is same-origin, so a wildcard only widens exposure."
            )
        # FIX: N7 - REDIS_URL must NOT be the in-process fakeredis in prod/staging:
        # FSM state, rate limits, idempotency keys and webhook dedup all live in Redis;
        # `memory://` would silently lose them on every process restart AND isolate
        # each gunicorn worker's view of state, breaking the whole distributed contract.
        if self.redis_url.startswith("memory"):
            raise RuntimeError(
                "REDIS_URL is 'memory://...' (fakeredis). This is dev/test-only — "
                "production MUST point at a real Redis so FSM/ratelimits/idempotency "
                "are shared across workers and survive restarts."
            )
        # FIX: N7 - DATABASE_URL must NOT be the dev SQLite file in prod/staging:
        # SQLite has no real concurrency (write-locks the whole file), no row-level
        # FOR UPDATE (with_for_update is a no-op there — see quota/billing), and the
        # `nullpool` engine config silently bypasses pooling. A prod deploy that
        # forgets to set DATABASE_URL would otherwise run on a single-file DB and
        # corrupt under any real concurrency.
        if self.database_url.startswith("sqlite"):
            raise RuntimeError(
                "DATABASE_URL is SQLite (file://) — dev/test-only. Production MUST "
                "use PostgreSQL (DATABASE_URL=postgresql+asyncpg://...) so row locks, "
                "concurrent writes and pooling all work as the code expects."
            )
        # FIX: AUDIT-29 - enforce admin_ip_allowlist and metrics_token in prod
        if self.is_public_deploy and not self.admin_ip_allowlist:
            raise RuntimeError(
                "ADMIN_IP_ALLOWLIST is empty — production admin API must be IP-restricted."
            )
        if self.is_public_deploy and not self.metrics_token:
            raise RuntimeError(
                "METRICS_TOKEN is empty — production /metrics endpoint must be auth-protected."
            )
        # FIX: AUDIT-P1 (P0) - if Stripe is enabled, its webhook signing secret MUST be
        # set. With an empty STRIPE_WEBHOOK_SECRET the SDK verifies against an empty HMAC
        # key, so anyone can forge a `paid` checkout.session.completed event and credit
        # themselves for free. Fail closed at boot rather than ship a forgeable webhook.
        if self.stripe_secret and not self.stripe_webhook_secret:
            raise RuntimeError(
                "STRIPE_SECRET is set but STRIPE_WEBHOOK_SECRET is empty — Stripe "
                "webhooks would be unverifiable and forgeable. Set STRIPE_WEBHOOK_SECRET "
                "in production."
            )

    @property
    def admin_ids(self) -> set[int]:
        return {
            int(x) for x in self.admin_user_ids.replace(" ", "").split(",") if x
        }

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()] or ["*"]

    @property
    def ai_base_url_allow(self) -> list[str]:
        return [h.strip().lower() for h in self.ai_base_url_allowlist.split(",") if h.strip()]

    @property
    def effective_webhook_secret(self) -> str:
        """The secret token used for Telegram webhook verification. Derived from
        the bot token if not explicitly configured, so it is always non-empty."""
        if self.webhook_secret:
            return self.webhook_secret
        import hashlib

        return hashlib.sha256(f"tg-wh:{self.bot_token}".encode()).hexdigest()

    @property
    def webhook_path(self) -> str:
        return "/webhook/telegram"

    @property
    def webhook_url(self) -> str:
        return f"{self.webhook_base_url.rstrip('/')}{self.webhook_path}"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s._require_prod_secret()
    return s


settings = get_settings()
