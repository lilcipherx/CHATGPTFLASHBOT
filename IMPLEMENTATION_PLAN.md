# GPT4Telegrambot — Clone Implementation Plan (Full-Stack)

> **Источник требований:** `GPT4Telegrambot_Reverse_Engineering_Report_v4/v5.md` (30 разделов, live-reverse-engineering от 15.06.2026).
> **Документ-план:** детальный план реализации production-клона с нуля до full-stack.
> **Дата плана:** 16.06.2026
> **Статус:** черновик v1 — требует ваших ответов на открытые вопросы (см. §16).

---

## 0. Зафиксированные решения (из брифинга)

| Решение | Выбор | Следствие для плана |
| --- | --- | --- |
| Стек бота/бэкенда | **Python + aiogram 3.x** | asyncio, FSM из коробки, единый язык бота + воркеров + API |
| Объём | **Полный full-stack сразу** | бот + AI + Mini App + платежи в одном монорепо, фазы идут параллельно где можно |
| AI-провайдеры | **Все реальные интеграции** | слой-роутер с адаптерами; для провайдеров без офиц. API — обёртки/партнёрский доступ (см. §7, риски) |
| Языки | **Все 8 (RU/EN/UZ/ES/FR/AR/PT-BR/ZH)** | i18n с первого дня, RU — эталон (дословно из отчёта) |
| Хостинг | **Docker Compose на VPS** | один compose-стек, путь к K8s оставлен открытым |
| Платежи | **Все 4 шлюза сразу** (Stars + СБП/Tribute + ЮКасса + Stripe) | единый PaymentProvider-интерфейс, вебхуки |
| Характер | **Реальный коммерческий продукт** | акцент на масштаб, антифрод, юр. документы, экономику маржи |
| Очередь задач (Q1) | **ARQ** (asyncio + Redis) | проще, нативно с aiogram; путь к Celery открыт |
| AI-ключи (Q5) | **Пользователь найдёт все нужные API** | адаптеры готовим с `is_available()`-фолбэком; подключаем по мере поступления ключей |
| Юр. лицо (Q14) | **Есть — для всех 4 шлюзов** | реально подключаем Stars + СБП(Tribute) + ЮКасса + Stripe |
| Бот (Q2) | **Один бот**, без резервного | — |
| Домен/регион (Q3/Q4) | **Домена нет → купим**; VPS в **ЕС** | влияет на доступ к API; для СБП/ЮКассы юр.лицо РФ через юр.прослойку |
| Higgsfield/Recraft (Q7/Q8) | **Higgsfield → маппим на Kling**; **Recraft — только в составе пакета** (без кнопки в /photo) | меньше адаптеров на старте |
| Рефералка/гейт (Q12/Q13) | **Рефералка НУЖНА**; **гейт-канал — свой** (не @Serch) | добавляем referral-логику и свой канал в `channel_gates` |
| Бренд (Q15) | **«ИИ Бот №1»** | бренд-нейм/тексты адаптируем под него |
| Объём (Q17) | **Реализуем ВСЁ из отчёта** | полный каталог сервисов, команд, экранов |
| Модерация (Q16) | **OpenAI Moderation + собственные правила** (дефолт) | фильтры 18+/насилие/дипфейки на уровне роутера |
| Админ-панель | **Web-админка (React + FastAPI admin API)** | RBAC+2FA; юзеры, платежи, тарифы, каталоги, рассылки, рефералы, модерация (§11A) |

---

## 1. Целевая архитектура

```
                          ┌────────────────────────────────────────────┐
                          │              Telegram (BotAPI)              │
                          └───────────────┬─────────────┬──────────────┘
                                  webhook  │             │ WebApp
                          ┌───────────────▼──┐      ┌────▼─────────────┐
                          │   Bot Gateway     │      │   Mini App SPA   │
                          │   (aiogram 3.x)   │      │   (React + TWA)  │
                          │   FSM, handlers   │      └────┬─────────────┘
                          └───────┬───────────┘           │ REST/WS
                                  │ internal calls         │
                          ┌───────▼────────────────────────▼────────────┐
                          │          Core Backend (FastAPI)              │
                          │  services: users, quota, packs, billing,     │
                          │  i18n, ai_router, jobs, templates            │
                          └───┬──────────┬───────────┬───────────┬───────┘
                              │          │           │           │
                   ┌──────────▼─┐  ┌─────▼─────┐ ┌───▼────┐  ┌───▼────────┐
                   │ PostgreSQL │  │   Redis    │ │ Celery │  │ AI Router  │
                   │ (источник  │  │ (context,  │ │ /ARQ   │  │ adapters:  │
                   │  истины)   │  │  rate-lim, │ │ workers│  │ OpenAI,    │
                   │            │  │  FSM-store)│ │ (видео,│  │ Anthropic, │
                   └────────────┘  └────────────┘ │ авы,   │  │ Google,    │
                                                  │ музыка)│  │ DeepSeek,  │
                                                  └────┬───┘  │ Kling,     │
                                                       │      │ Minimax,   │
                                              ┌────────▼────┐ │ Pika,      │
                                              │ Object store│ │ Seedream,  │
                                              │ (S3/MinIO)  │ │ BFL/FLUX,  │
                                              │ результаты  │ │ Suno,      │
                                              └─────────────┘ │ Perplexity │
                                                              └────────────┘
              Платежи:  Stars (BotAPI) · Tribute(СБП) · YooKassa · Stripe  → webhooks → billing
```

**Ключевые принципы:**
- **PostgreSQL — единственный источник истины** (юзеры, подписки, балансы пакетов, транзакции, шаблоны, jobs).
- **Redis** — эфемерное: rolling-контекст диалога (`context:{user_id}`), rate-limits, FSM-storage aiogram, кэш каталогов шаблонов.
- **Celery/ARQ воркеры** — все долгие генерации (видео, аватарки ~15 мин, музыка) идут асинхронно; бот остаётся отзывчивым.
- **AI Router** — единый интерфейс `generate()` поверх 12+ адаптеров; смена провайдера не трогает хендлеры.
- **Bot и Mini App** делят один Core Backend и одну БД (как в оригинале).

---

## 2. Технологический стек

| Слой | Технология | Примечание |
| --- | --- | --- |
| Bot framework | aiogram 3.x | FSM, роутеры, middlewares |
| Backend API | FastAPI + uvicorn/gunicorn | REST для Mini App + внутренние сервисы |
| ORM / миграции | SQLAlchemy 2.x (async) + Alembic | |
| БД | PostgreSQL 16 | |
| Кэш/очередь-стейт | Redis 7 | + RedisStorage для aiogram FSM |
| Очередь задач | **ARQ** (broker=Redis) | выбрано (Q1); нативно с asyncio/aiogram |
| Object storage | MinIO (S3-совместимое) | результаты генераций, превью шаблонов |
| Mini App | React 18 + TypeScript + Vite + `@twa-dev/sdk` | Telegram WebApp |
| Админ-панель | React 18 + TypeScript + Vite + FastAPI admin API (JWT+2FA, RBAC) | отдельный билд/поддомен; опц. SQLAdmin |
| i18n | `fluent`/`gettext` (.ftl или .po) | 8 локалей |
| Платежи | aiogram Payments (Stars) + YooKassa SDK + Stripe SDK + Tribute API | |
| Контейнеризация | Docker + docker-compose | |
| Обратный прокси | Caddy/Nginx (TLS, webhook-эндпоинты) | |
| Наблюдаемость | Prometheus + Grafana + Sentry | логи structlog |
| CI/CD | GitHub Actions (lint, test, build, deploy) | |
| Тесты | pytest + pytest-asyncio + aiogram test utils | |

---

## 3. Структура монорепо

```
CHATGPTFLASH/
├── docker-compose.yml
├── docker-compose.prod.yml
├── .env.example
├── README.md
├── IMPLEMENTATION_PLAN.md          # этот файл
│
├── bot/                            # aiogram-приложение
│   ├── main.py
│   ├── handlers/                   # по разделам: start, chat, photo, video, music,
│   │   │                          #   model, settings, account, premium, payments, search
│   ├── keyboards/                  # reply + inline клавиатуры
│   ├── states/                     # FSM-состояния (StatesGroup)
│   ├── middlewares/                # i18n, quota-check, gate-check, throttling, db-session
│   ├── filters/                    # subscription, premium, pack-balance
│   └── texts/                      # ссылки на i18n-ключи
│
├── core/                           # бизнес-логика (общая для bot + api)
│   ├── models/                     # SQLAlchemy модели
│   ├── services/                   # users, quota, packs, billing, templates, jobs
│   ├── ai_router/                  # абстракция + адаптеры провайдеров
│   │   ├── base.py                 # интерфейсы TextProvider/ImageProvider/...
│   │   ├── openai_adapter.py
│   │   ├── anthropic_adapter.py
│   │   ├── google_adapter.py       # Gemini + Veo + Lyria
│   │   ├── deepseek_adapter.py
│   │   ├── perplexity_adapter.py
│   │   ├── kling_adapter.py
│   │   ├── minimax_adapter.py
│   │   ├── pika_adapter.py
│   │   ├── seedream_adapter.py
│   │   ├── bfl_flux_adapter.py
│   │   ├── midjourney_adapter.py
│   │   └── suno_adapter.py
│   ├── payments/                   # PaymentProvider интерфейс + 4 реализации
│   ├── i18n/                       # локали .ftl
│   └── config.py                   # pydantic-settings
│
├── api/                            # FastAPI для Mini App + админки
│   ├── main.py
│   ├── routers/                    # effects, profile, billing, generate
│   ├── admin/                      # admin API: auth(RBAC+2FA), users, payments,
│   │   │                          #   pricing, catalogs, broadcasts, referrals, moderation
│   └── deps.py                     # auth: initData (Mini App) / JWT (админка)
│
├── workers/                        # Celery/ARQ задачи
│   ├── video_tasks.py
│   ├── avatar_tasks.py
│   ├── music_tasks.py
│   └── billing_tasks.py            # авто-продление, экспирация подписок (cron)
│
├── miniapp/                        # React SPA (Telegram WebApp)
│   ├── src/
│   │   ├── pages/ (Home, Trends, Profile)
│   │   ├── components/
│   │   └── api/
│   └── vite.config.ts
│
├── admin/                          # React SPA админ-панель (отдельный билд)
│   ├── src/
│   │   ├── pages/ (Dashboard, Users, Payments, Pricing, Catalogs,
│   │   │           Broadcasts, Referrals, Providers, Moderation, Audit)
│   │   ├── components/
│   │   └── api/
│   └── vite.config.ts
│
├── migrations/                     # Alembic
├── scripts/                        # seed шаблонов Kling/effects, импорт каталогов
└── tests/
```

---

## 4. Модель данных (расширенная схема)

Базируется на §17 отчёта + дополнения для production (антифрод, идемпотентность платежей, рефералы/гейт-подписки).

```sql
-- Пользователи и конфиг (per-user settings)
users(
  user_id BIGINT PK, username VARCHAR, language_code VARCHAR(5) DEFAULT 'ru',
  selected_model VARCHAR(50) DEFAULT 'gemini_3_1_flash',
  custom_role TEXT, role_enabled BOOL DEFAULT false,
  context_enabled BOOL DEFAULT true,
  voice_name VARCHAR(20) DEFAULT 'alloy', voice_enabled BOOL DEFAULT false,
  sub_tier VARCHAR(20),                  -- null | premium | premium_x2
  sub_expires TIMESTAMPTZ,
  text_req_week INT DEFAULT 0, week_start TIMESTAMPTZ,
  mini_app_effects_week INT DEFAULT 0, mini_app_week_start TIMESTAMPTZ,
  diamonds INT DEFAULT 0,                -- 💎 валюта Mini App
  is_channel_subscribed BOOL DEFAULT false,  -- гейт @Serch
  referred_by BIGINT, is_banned BOOL DEFAULT false,
  created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ
)

pack_balances(user_id BIGINT FK, image_credits INT DEFAULT 0,
              video_credits INT DEFAULT 0, music_credits INT DEFAULT 0)

-- Платежи (с идемпотентностью)
transactions(
  tx_id UUID PK, user_id BIGINT FK,
  product VARCHAR(30),                   -- premium|premium_x2|image_pack|video_pack|music_pack|avatar|diamonds
  duration_months INT, qty INT, amount INT, currency VARCHAR(10),  -- stars|rub|usd
  gateway VARCHAR(20),                   -- stars|sbp_tribute|yookassa|stripe
  gateway_tx_id VARCHAR(120) UNIQUE,     -- идемпотентность вебхуков
  status VARCHAR(20),                    -- pending|paid|failed|refunded
  credits_added INT, created_at TIMESTAMPTZ, paid_at TIMESTAMPTZ
)

-- Асинхронные задачи генерации
generation_jobs(
  job_id UUID PK, user_id BIGINT FK, service VARCHAR(50), model_variant VARCHAR(50),
  params JSONB, cost_credits INT, pack_type VARCHAR(10),  -- image|video|music
  status VARCHAR(20),                     -- pending|processing|complete|failed
  result_file_id VARCHAR(200), result_url VARCHAR(500),
  provider_job_id VARCHAR(120), error TEXT,
  created_at TIMESTAMPTZ, completed_at TIMESTAMPTZ
)

-- Контекст диалога — Redis, не SQL:
--   key context:{user_id} -> JSON [{q,a}, ...]  (rolling, /deletecontext = DEL)

-- Каталоги шаблонов
kling_effects_templates(template_id INT PK, page INT, position INT,
                        name_ru VARCHAR(100), name_i18n JSONB, is_new BOOL, preview_url VARCHAR(500))
kling_motion_templates(template_id INT PK, page INT, position INT,
                        name_ru VARCHAR(100), name_i18n JSONB, preview_url VARCHAR(500))
mini_app_photo_effects(effect_id INT PK, category VARCHAR(20),  -- all|female|male|children|couple
                        name_ru VARCHAR(100), name_i18n JSONB, thumbnail_url VARCHAR(500),
                        badge VARCHAR(10), gen_count INT DEFAULT 0, is_ad BOOL DEFAULT false)
mini_app_video_effects(effect_id INT PK, category VARCHAR(20),  -- all|dance|emotion|effect|transform
                        name_ru VARCHAR(100), provider VARCHAR(20),  -- kling|higgsfield|pika
                        thumbnail_url VARCHAR(500), gen_count INT DEFAULT 0)

-- Рефералы (Q12)
referrals(id BIGSERIAL PK, referrer_id BIGINT, referred_id BIGINT UNIQUE,
          reward_type VARCHAR(20), reward_amount INT,
          status VARCHAR(20),                 -- pending|rewarded|rejected
          created_at TIMESTAMPTZ, rewarded_at TIMESTAMPTZ)

-- Аналитика/антифрод
usage_log(id BIGSERIAL PK, user_id BIGINT, action VARCHAR(50), meta JSONB, created_at TIMESTAMPTZ)
channel_gates(channel VARCHAR(50), is_active BOOL)  -- какие каналы требуем для free-квоты (свой канал — Q13)

-- Тарифы/конфиг (правится без деплоя)
pricing(key VARCHAR(50) PK, value JSONB)         -- цены пакетов, мультипликаторы, награды рефералов

-- Админ-панель
admin_users(id BIGSERIAL PK, email VARCHAR UNIQUE, password_hash VARCHAR,
            totp_secret VARCHAR, role VARCHAR(20),       -- superadmin|admin|support|moderator
            is_active BOOL DEFAULT true, last_login TIMESTAMPTZ, created_at TIMESTAMPTZ)
admin_audit_log(id BIGSERIAL PK, admin_id BIGINT, action VARCHAR(60),
                target_type VARCHAR(40), target_id VARCHAR(60),
                before JSONB, after JSONB, ip VARCHAR(45), created_at TIMESTAMPTZ)
broadcasts(id BIGSERIAL PK, admin_id BIGINT, segment JSONB, content JSONB,
           scheduled_at TIMESTAMPTZ, status VARCHAR(20),  -- draft|scheduled|sending|done|failed
           sent INT DEFAULT 0, failed INT DEFAULT 0, created_at TIMESTAMPTZ)
promo_codes(code VARCHAR(40) PK, reward_type VARCHAR(20), reward_amount INT,
            max_uses INT, used INT DEFAULT 0, expires_at TIMESTAMPTZ, is_active BOOL)
```

---

## 5. Конфигурация и секреты (`.env`)

```
# Telegram
BOT_TOKEN=
WEBHOOK_BASE_URL=
MINIAPP_URL=

# DB / infra
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://redis:6379/0
S3_ENDPOINT= S3_KEY= S3_SECRET= S3_BUCKET=

# AI providers
OPENAI_API_KEY=          # GPT-5.x, GPT Image 2, TTS
ANTHROPIC_API_KEY=       # Claude 4.8/4.6
GOOGLE_API_KEY=          # Gemini 3.x, Veo 3.1, Lyria 3
DEEPSEEK_API_KEY=
PERPLEXITY_API_KEY=
KLING_API_KEY=           # Kuaishou (AI/Motion/Effects)
MINIMAX_API_KEY=
PIKA_API_KEY=
SEEDREAM_API_KEY=
BFL_API_KEY=             # FLUX 2
MIDJOURNEY_API_KEY=      # неофиц. обёртка/партнёр
SUNO_API_KEY=

# Payments
TRIBUTE_API_KEY=         # СБП
YOOKASSA_SHOP_ID= YOOKASSA_SECRET=
STRIPE_SECRET= STRIPE_WEBHOOK_SECRET=

# Business config
FREE_TEXT_WEEKLY=100
FREE_MINIAPP_WEEKLY=25
PREMIUM_DAILY=100
PREMIUM_X2_DAILY=200
GATE_CHANNEL=@Serch
SUPPORT_CONTACT=@i_abramov_gpt
```

Все бизнес-числа (квоты, цены, мультипликаторы стоимости) выносим в **config + БД-таблицу `pricing`**, чтобы менять без деплоя.

---

## 6. FSM-карта состояний (aiogram)

Из §3.1, §21, §30 отчёта. Группы состояний:

```
MainSG:        idle (chat)            # plain text → AI
SearchSG:      waiting_query
PhotoSG:       menu → service_config(model/quality/ratio/seed) → awaiting_input
VideoSG:       menu → service_config(...) → awaiting_input → (async job)
MusicSG:       menu → awaiting_prompt
ModelSG:       selecting
SettingsSG:    menu → role_input | voice_select | lang_select | context_toggle
PremiumSG:     product_select → duration_select → gateway_select → invoice
PackBuySG:     pack_select(image/video/music) → qty_select → gateway_select → invoice
AvatarSG:      info → buy → awaiting_selfie → (async ~15min)
FaceSwapSG:    step1_target_photo → step2_source_face
UpscaleSG:     choose_x2_x4 → awaiting_image
KlingEffectSG: browse(page n/7) → effect_selected → awaiting_photo
KlingMotionSG: mode_select → template_browse | custom_video_photo → awaiting_input
```

**Гейты как middleware (не состояния):**
- `Gate#1 WeeklyQuota` — текст/фото/распознавание → проверка подписки на канал ИЛИ premium (§24C, §30).
- `Gate#2 PackEmpty` — pack-сервис при балансе 0 → «Пополнить» (§24C).
- `Gate#3 Premium` — голос, документы, premium-модели (§30A).
- `No gate` — /start, /help, /account, навигация, стикеры (игнор).

---

## 7. AI Router — слой абстракции провайдеров

**Интерфейсы** (`core/ai_router/base.py`):

```python
class TextProvider(Protocol):
    async def chat(self, messages, model, system=None, **opts) -> TextResult

class ImageProvider(Protocol):
    async def generate(self, prompt, count, ratio, quality, refs=None, seed=None) -> list[ImageResult]
    async def edit(self, prompt, images) -> list[ImageResult]

class VideoProvider(Protocol):
    async def submit(self, params) -> provider_job_id           # async
    async def poll(self, provider_job_id) -> JobStatus

class TTSProvider(Protocol):
    async def speak(self, text, voice) -> AudioResult
```

**Маппинг моделей → адаптер → стоимость** (из §5, §22):

| Сервис/модель | Адаптер | Тариф (генерации) | Пул |
| --- | --- | --- | --- |
| GPT-5 mini / 5.4 / 5.5 | openai | 1 / 1 / **3** | weekly text quota |
| Claude 4.8 Opus / 4.6 Sonnet | anthropic | **5** / 1 | weekly (premium) |
| Gemini 3.1/3.5 Flash | google | 1 | weekly |
| DeepSeek V4 / V4 Pro | deepseek | 1 | weekly |
| Perplexity (/s) | perplexity | 1 | weekly |
| GPT Image 2 | openai | weekly quota (НЕ pack) | weekly |
| Nano Banana 2 / Pro | google | 1K=2, 2K=3, 4K=4 | NB2=weekly, Pro=image pack |
| Seedream 4.5/5 | seedream | pack default | image pack |
| Midjourney V7/V8.1 | midjourney | pack default | image pack |
| FLUX 2 / Flex / Pro / Max | bfl | 1 / 2 / 1 / 2 | image pack |
| Face Swap | (custom) | 1 | image pack |
| Upscale X2/X4 | (Real-ESRGAN) | 2 / 4 | image pack |
| Kling AI 3.0/O1/2.6/2.5T | kling | 5с=1,10с=2,15с=3; 4K ×2 | video pack |
| Veo 3.1 / Fast | google | 1; 4K=2 | video pack |
| Grok Imagine | xai | create=1, edit=2 | video pack |
| Minimax Hailuo | minimax | pack default | video pack |
| Pika 2.5 | pika | 5/720=1 … 10/1080=3 | video pack |
| Seedance 2.0 | seedance | pack default | video pack |
| Suno V5.5 / Lyria 3 | suno / google | pack default | music pack |
| TTS (12 голосов) | openai | premium | — |

**Риски доступа к API (из §19) — обработать в адаптерах с фолбэком:**
- Midjourney — нет офиц. API → неофициальная обёртка/партнёрский доступ; адаптер изолирует риск.
- Kling/Kuaishou — гео-ограничения; возможен прокси-регион.
- Veo 3.1 — Google partner/waitlist.
- Suno — коммерческий API, лимиты по ёмкости.
Каждый адаптер реализует `is_available()` и graceful-degradation (сообщение «сервис временно недоступен»).

---

## 8. Система квот, пакетов и тарифов (бизнес-логика)

**Двойной счётчик квот (§10.1):**
- `text_req_week` — чат + /s + распознавание + документы; лимит free=100/нед, premium=100-200/день. Сброс еженедельный (по `week_start`).
- `mini_app_effects_week` — только Mini App фотоэффекты; free=25/нед. Независимый счётчик.

**Diamonds (💎)** — отдельная валюта Mini App (§23F): фотоэффект 1K/2K/4K = 2/3/4 💎, видеоэффект = 1 💎. После исчерпания 25/нед — списываются 💎/кредиты.

**Пакеты (§26C, ledger в `pack_balances`):**
- Изображения: Midjourney, Seedream, Recraft, FLUX, Face Swap (НЕ NB2/GPT Image 2).
- Видео: Kling, Veo, Seedance, Grok, Hailuo, Pika, видеоэффекты.
- Песни: Suno, Lyria.

**Транзакционная логика списания:** атомарно (SELECT FOR UPDATE / Redis-lock) — проверка баланса → списание → submit job → при ошибке провайдера возврат кредитов.

**Цены (§11, §26) — таблица `pricing`:**
- Premium: 600/1200/2000/3000⭐; Premium X2: 900/1800/3000/4500⭐.
- Image pack: 50/100/200/500 → 250/450/800/1750⭐.
- Video pack: 2/10/20/50 → 150/500/900/2000⭐.
- Music pack: 20/50/100 → 250/500/900⭐.
- Avatar: 200⭐ (one-time, /ava).

**Cron-задачи (workers/billing_tasks):** еженедельный сброс квот, проверка экспирации подписок, авто-продление, напоминания.

### 8.1 Реферальная программа (новое, вне отчёта — Q12)

Механика (черновик, числа в `pricing`/config — настраиваются без деплоя):
- **Ссылка:** deep-link `https://t.me/<bot>?start=ref_<user_id>`; парсится в `/start`, пишется в `users.referred_by` (только для новых юзеров, защита от self-ref).
- **Награда рефереру:** при ПЕРВОЙ оплате приглашённого — бонус рефереру (дефолт: +N кредитов изображений ИЛИ % от суммы в 💎/кредитах). Тип награды — на твоё решение.
- **Награда приглашённому:** приветственный бонус (дефолт: +неделя расширенной квоты или стартовые кредиты).
- **Анти-абуз:** награда только после успешного `successful_payment`/webhook (не за регистрацию); лимит наград на реферера/день; проверка устройства/айпи через `usage_log`.
- **Таблицы:** `referrals(referrer_id, referred_id, reward_type, reward_amount, status, created_at, rewarded_at)` + поле `users.referred_by` (уже в §4).
- **UI:** раздел «Пригласить друга» в Профиле Mini App и/или команда `/invite` со ссылкой + счётчиком приглашённых и заработанного.

> **Нужно твоё решение позже:** размер и тип награды (кредиты / 💎 / % / дни premium). Заложим конфигом, дефолт — +10 кредитов изображений рефереру за первую оплату друга.

---

## 9. Платёжный модуль (4 шлюза)

**Единый интерфейс** `PaymentProvider`: `create_invoice(product, amount, user) -> InvoiceData`, `verify_webhook(payload) -> PaymentEvent`.

| Шлюз | Реализация | Поток |
| --- | --- | --- |
| Telegram Stars | aiogram `send_invoice` (XTR) | нативный инвойс → `pre_checkout_query` → `successful_payment` → активация |
| СБП | Tribute API | web-view → вебхук |
| ЮКасса | yookassa SDK | web-view → вебхук |
| Stripe | stripe SDK | Checkout → вебхук + signature verify |

**3-шаговый FSM покупки (§12.1):** сервис → длительность/кол-во → шлюз → инвойс. Идемпотентность по `gateway_tx_id`. Вебхуки — отдельные FastAPI-эндпоинты с верификацией подписи.

---

## 10. i18n (8 языков)

- Эталон — **RU**, дословно из отчёта (§15, §28, §29 и др.).
- Формат: Fluent `.ftl` по локали; ключи = смысловые (`start.welcome`, `account.weekly`, `gate.subscription` ...).
- `LanguageMiddleware` подставляет локаль из `users.language_code` (выбор в /settings → Язык интерфейса, 8 опций).
- AI-ответы остаются на языке пользователя (автоопределение), переводится только UI.
- EN/UZ/ES/FR/AR/PT-BR/ZH — машинный перевод + ручная вычитка ключевых экранов (start, premium, gates).

---

## 11. Mini App (React + Telegram WebApp)

3 таба (§13, §23):
- **Главная** — баннер GPT Image 2 (бесплатные генерации), «Создать изображение», карусель Видеоэффектов (3 + «Смотреть все»).
- **Тренды** — Фотоэффекты, 5 категорий (Все/Женские/Мужские/Детские/Общие), карточки с badge (NEW/TOP/PRO/AD), детальная «Создать фото» (качество 1K/2K/4K, 11 соотношений, ✨ Сгенерировать N💎).
- **Профиль** — подписка, балансы пакетов, счётчик 💎/квоты, покупки (4 шлюза), «Подключить Премиум».

**Видеоэффекты:** галерея (Все/Танцы/Эмоции/Эффекты/Превращения), провайдеры kling/higgsfield/pika, флэт-цена 1💎, тоггл звука, загрузка фото.

**Лимиты:** ≤10 фото, 30 МБ/фото, бесконечный скролл, виртуализация. Auth — Telegram `initData` (HMAC-проверка на бэкенде).

---

## 11A. Админ-панель (Web)

Отдельное веб-приложение для управления продуктом. Реюзает стек Mini App (React+TS+Vite) + отдельный защищённый `api/admin/` роутер на FastAPI. Деплоится на поддомене `admin.<domain>` за Caddy, доступ только по allow-list IP + auth.

### 11A.1 Аутентификация и роли (RBAC)
- Вход: email+пароль (argon2) **+ обязательная 2FA (TOTP)**; сессии — JWT (короткий access + refresh), httpOnly cookie.
- Доступ ограничен по IP allow-list на уровне прокси + rate-limit на логин.
- **Роли:**
  - `superadmin` — всё, включая управление админами и редактор цен.
  - `admin` — пользователи, платежи, рассылки, каталоги, без управления админами.
  - `support` — просмотр юзеров, выдача компенсаций (кредиты/дни) в лимите, без редактора цен.
  - `moderator` — очередь модерации, баны контента/юзеров.
- Каждое чувствительное действие пишется в `admin_audit_log` (кто/что/когда/до→после).

### 11A.2 Модули админки

| Модуль | Возможности |
| --- | --- |
| **Дашборд** | MAU/DAU, выручка (по шлюзам/продуктам), конверсия free→paid, активные подписки, исчерпание квот, нагрузка на AI-провайдеров, статус очереди задач |
| **Пользователи** | поиск (id/username), карточка: профиль, подписка, балансы, история транзакций и генераций; действия: бан/разбан, выдать/списать кредиты, выдать premium на N дней, сбросить квоту, очистить контекст |
| **Платежи/транзакции** | список, фильтры по шлюзу/статусу, детали вебхуков, **возвраты (refund)** где шлюз позволяет, ручное подтверждение «зависших» pending |
| **Тарифы (`pricing`)** | редактор цен подписок/пакетов, мультипликаторов стоимости моделей, наград рефералов — применяется без деплоя |
| **Каталоги шаблонов** | CRUD Kling Effects / Kling Motion / фото- и видеоэффектов Mini App: имена (i18n), превью, порядок/страницы, badge (NEW/TOP/PRO), AD-слот, вкл/выкл |
| **Гейт-каналы** | управление списком обязательных каналов для free-квоты (свой канал — Q13), вкл/выкл |
| **Рассылки (broadcast)** | массовая рассылка по сегментам (все / free / premium / по языку / неактивные); планировщик, throttling под лимиты Telegram, медиа+кнопки, превью, отчёт о доставке/блокировках |
| **Рефералы** | топ-рефереры, начисленные награды, ручная корректировка, анти-абуз флаги |
| **AI-провайдеры** | статус `is_available`, ручное вкл/выкл сервиса (kill-switch при сбое API), просмотр ошибок адаптеров |
| **Модерация** | очередь флагнутого контента (18+/насилие/дипфейк), решения, баны |
| **Промокоды** *(опц.)* | генерация кодов на кредиты/дни premium, лимиты использования, срок |
| **Логи/аудит** | `usage_log`, `admin_audit_log`, экспорт |

### 11A.3 Технически
- `api/admin/` — отдельный FastAPI APIRouter с RBAC-зависимостями, изолирован от Mini App API.
- Тяжёлые операции (рассылка на миллионы, экспорт) → задачи **ARQ**, не блокируют запрос.
- Для быстрого «сырого» доступа к БД на старте — опционально **SQLAdmin** (autogenerated CRUD), но основной UI — кастомный React-админ.
- Безопасность: CSRF на cookie-сессии, аудит, принцип наименьших привилегий, маскирование PII в логах.

> **Нужно твоё решение позже:** список email’ов первых админов и их роли; лимиты компенсаций для роли `support`; нужны ли промокоды на старте.

---

## 12. Детальные спецификации команд

> Тексты — **дословно из отчёта** (§15, §28, §29). Здесь — поведение + что подтвердить у вас (§16).

| Команда | Текст/экран | Поведение | Источник |
| --- | --- | --- | --- |
| `/start` | §28 verbatim | без гейта; persistent reply-keyboard (8 кнопок §27); deep-link парсинг рефералов | §28, §27 |
| `/help` | §15.2 verbatim | список + форматы документов, лимиты, /chirp | §15.2 |
| plain text | — | AI-чат выбранной моделью; кнопки 🔊(premium)/🌐; rolling-контекст | §3.2 |
| `/s` | «Пожалуйста, подождите…» → 🔥 Просмотр | Perplexity + Instant View; квота | §3.2 |
| `/photo` | §15.4 verbatim | 9 сервисов + Закрыть; вход в PhotoSG | §15.4, §21B |
| `/video` | §15.5 verbatim | 9 сервисов + Закрыть; VideoSG | §15.5, §21A |
| `/music` | §15.6 verbatim | Suno/Lyria; paywall если нет пакета | §15.6 |
| `/model` | §15.7 verbatim | 9 моделей, ✅ активная, premium-гейт | §15.7 |
| `/settings` | §15.3 verbatim | 6 кнопок: модель/роль/контекст/голос/язык | §9, §15.3 |
| `/account` | §29 verbatim | статистика, балансы, 🚀 Подключить Премиум | §29 |
| `/premium` | §15.9 verbatim | 2 продукта × 4 длительности → шлюз | §11, §26 |
| `/deletecontext` | §15.10 verbatim | DEL context:{user_id}; позиция #4 в меню | §15.10, §25 |
| `/privacy` | §15.11 | 2 teletype-ссылки | §15.11 |
| `/wow` (hidden) | — | шорткат → GPT Image 2 | §25A |
| `/ava` (hidden) | §21B verbatim | шорткат → Набор аватарок (200⭐) | §25A |
| `/chirp` (hidden) | — | алиас музыки | §4.2, §8 |
| `/Midjourney` (hidden) | — | прямой Midjourney | §4.2 |

**Гейт-сообщения (дословно §24C, §30):** Gate#1 (подписка на @Serch, 3 кнопки), Gate#2 («Пополнить», 1 кнопка), Gate#3 (premium для голоса/документов). Стикеры — молчаливый игнор.

---

## 13. Фазы реализации (роадмап)

> Full-stack, но порядок снижает риск. Каждая фаза = рабочий инкремент.

### Фаза 0 — Каркас (≈3-5 дней)
- Монорепо, docker-compose (postgres, redis, minio, bot, api), .env, Alembic init.
- aiogram bootstrap + webhook, FastAPI bootstrap, structlog, Sentry.
- БД-модели + миграции (§4), `users` upsert на /start.
- i18n-каркас (RU полный + пустые локали), LanguageMiddleware.
- CI: lint (ruff) + pytest + build.

### Фаза 1 — Ядро текста + аккаунт (≈1-1.5 нед)
- /start, /help, persistent reply-keyboard (§27), /account, /deletecontext, /privacy.
- Plain-text чат через AI Router (OpenAI/Gemini/DeepSeek real), rolling-контекст (Redis).
- /model (9 моделей, гейт premium), /settings (роль/контекст/голос/язык).
- Квоты: weekly text counter + сброс; Gate#1 (подписка на канал), Gate#3 (premium-модели).
- Перевод-кнопка 🌐.

### Фаза 2 — Поиск + голос + документы (≈1 нед)
- /s (Perplexity + Instant View).
- TTS (12 голосов OpenAI), кнопка 🔊, превью голоса (premium-гейт).
- Документы (PDF/DOCX/XLSX… extract, 3 генерации, premium).
- Завершить 8 локалей для основных экранов.

### Фаза 3 — Изображения (≈1.5-2 нед)
- Image pack ledger + покупка + списание (атомарно).
- GPT Image 2 (weekly), NB2/NBPro, Seedream, Midjourney, FLUX 2 (4 варианта, seed), Face Swap (2 шага), Upscale X2/X4.
- Avatar pack (/ava, 200⭐, async ~15 мин, очередь).
- Все per-service sub-menus и status-text (§21B).
- Gate#2 (pack empty).

### Фаза 4 — Видео (≈2-3 нед)
- Video pack ledger.
- Адаптеры: Seedance 2.0, Veo 3.1, Kling AI (4), Minimax Hailuo, Grok Imagine, Pika 2.5.
- Kling Effects (74 шаблона, 7 страниц, пагинация) + Kling Motion (13+ шаблонов, custom-режим).
- Async job-очередь + poll + доставка результата + возврат кредитов при ошибке.
- Полные sub-menus (§21A).

### Фаза 5 — Музыка + платежи (≈1.5 нед)
- Music pack + paywall.
- Suno V5.5, Lyria 3 Pro, /chirp.
- /premium (2 продукта × 4 длительности), pack-покупки.
- **4 шлюза**: Stars + Tribute(СБП) + ЮКасса + Stripe, вебхуки, идемпотентность.
- Cron: сброс квот, экспирация/продление подписок.

### Фаза 6 — Mini App (≈2-3 нед)
- React SPA, 3 таба, auth по initData.
- Фотоэффекты (категории, качество, соотношения, 💎), Видеоэффекты (провайдеры, 1💎).
- Профиль: балансы, покупки (4 шлюза), апгрейд.
- Лимиты загрузки (10 фото / 30 МБ), seed-скрипты каталогов эффектов.

### Фаза 6.5 — Админ-панель (≈2-2.5 нед)  *(§11A)*
- Admin API: auth (JWT + 2FA TOTP), RBAC (4 роли), IP allow-list, `admin_audit_log`.
- React-админ: Дашборд, Пользователи, Платежи (+refund), Тарифы (`pricing`), Каталоги шаблонов, Гейт-каналы, Рефералы, AI-провайдеры (kill-switch), Модерация.
- **Рассылки**: сегменты, планировщик, throttling под лимиты Telegram, отчёты (через ARQ).
- Промокоды (опц.). Управление админами (superadmin).
> Можно вести частично параллельно с Фазами 3-6, т.к. админка читает уже существующие таблицы.

### Фаза 7 — Прод-готовность (≈1.5-2 нед)
- Антифрод (rate-limits, дубликаты платежей, бан), usage_log, аналитика.
- Нагрузочное тестирование, кэширование каталогов, индексы БД.
- Юр. документы (соглашение, политика), модерация контента (фильтры 18+/дипфейки как в Grok/Seedance).
- Grafana-дашборды, алерты, бэкапы БД, runbook.
- docker-compose.prod + деплой на VPS + TLS (Caddy).

**Грубая оценка:** ~11-15 недель силами небольшой команды; критический путь — видео-адаптеры и доступ к API (Midjourney/Kling/Veo/Suno).

---

## 14. DevOps / Docker Compose

`docker-compose.yml` сервисы: `postgres`, `redis`, `minio`, `bot`, `api`, `worker` (ARQ), `beat` (cron), `miniapp` (build), `admin` (build), `caddy` (TLS + reverse-proxy: webhook / api / miniapp / `admin.<domain>` с IP allow-list).

CI/CD: GitHub Actions → lint/test → build images → push registry → deploy (ssh/compose pull+up). Секреты — GitHub Secrets / VPS .env (не в репо).

Бэкапы: `pg_dump` по cron в S3; политика ретеншена.

---

## 15. Тестирование

- **Unit:** quota-логика, списание кредитов, ценообразование, i18n-ключи.
- **Integration:** aiogram-хендлеры (mock Bot), вебхуки платежей (sandbox Stripe/ЮКасса).
- **AI-адаптеры:** контрактные тесты с VCR-кассетами/моками; `is_available` фолбэки.
- **E2E:** сценарии — onboarding, чат+квота-гейт, покупка premium (Stars sandbox), генерация изображения с pack, async-видео job.
- **Mini App:** Vitest + Playwright (initData mock).

---

## 16. Открытые вопросы — нужны ваши решения

> Тексты команд у меня есть. Ниже — то, чего НЕТ в отчёте и что влияет на реализацию. Ответьте по пунктам (можно кратко «Q1: …, Q2: …»).

**Все вопросы §16 закрыты** ✅ (см. таблицу решений в §0). Сводка:

| Q | Решение |
| --- | --- |
| Q1 | ARQ (asyncio + Redis) |
| Q2 | Один бот, без резервного |
| Q3/Q4 | Домена нет → купим; VPS в ЕС |
| Q5 | Все API-ключи пользователь найдёт; адаптеры с `is_available()`-фолбэком |
| Q6 | Midjourney — неофиц. обёртка/партнёр; риск изолирован в адаптере |
| Q7/Q8 | Higgsfield → маппим на Kling; Recraft — только в пакете (без кнопки в /photo) |
| Q9 | Suno/Lyria = **pack default (1 кредит/песня)** — см. ниже |
| Q10 | Premium 100/день, Premium X2 200/день; X2 = удвоенный дневной лимит, модели те же (§26B) |
| Q11 | 💎 в Mini App = кредиты image pack; **отдельная продажа 💎 не предусмотрена** — см. ниже |
| Q12/Q13 | Рефералка НУЖНА; гейт-канал — свой |
| Q14 | Юр. лицо есть для всех 4 шлюзов |
| Q15 | Бренд: «ИИ Бот №1» |
| Q16 | Модерация: OpenAI Moderation + собственные правила |
| Q17 | Реализуем ВСЁ из отчёта (полный каталог) |

### Два числа, которых физически НЕТ в отчёте (подставлены дефолты из его логики)

> Отчёт сам это признаёт — фиксирую дефолт, при желании скорректируешь одной строкой в таблице `pricing`.

- **Стоимость песни (Q9).** §22C дословно: *«exact per-song cost not shown in popups… likely flat pack deduction»*. Дефолт: **1 кредит = 1 песня** (пакеты 20/50/100 из §26C).
- **Продажа 💎 (Q11).** §23F дословно: *«After quota: 3 💎 per gen (implied)»* — отдельного «магазина алмазов» в отчёте нет. Дефолт: 💎 тождественны кредитам пакета изображений (фотоэффект 1K/2K/4K = 2/3/4, видеоэффект = 1, §23F); докупаются через image pack. Если нужен отдельный SKU «алмазы» — добавим в `pricing`.

---

### Что дальше
Все решения зафиксированы — можно стартовать **Фазу 0 (каркас репозитория)**:
1. структура монорепо + `docker-compose.yml` + `.env.example`;
2. aiogram + FastAPI bootstrap, подключение PostgreSQL/Redis/MinIO;
3. SQLAlchemy-модели + первая Alembic-миграция;
4. i18n-каркас (RU полностью) + middlewares (i18n, quota, gate).
Затем Фаза 1 — ядро текста + аккаунт с дословными RU-текстами из отчёта.
