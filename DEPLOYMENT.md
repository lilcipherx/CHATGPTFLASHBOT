# Деплой в продакшн — пошаговый runbook

Закрывает 7 операционных пунктов перед запуском. Команды копируются как есть;
места с `# ⟵ ВПИШИ` требуют твоих реальных значений (домен, токены, ключи).

> Имена переменных взяты из `core/config.py` — это ровно то, что читает приложение.
> Файл `.env` в репозиторий НЕ коммитится (он в `.gitignore`). Секреты — только в нём.

---

## 0. Что уже сделано кодом / проверено

- ✅ Конфиг сам падает на небезопасных дефолтах в public-deploy (`_require_prod_secret`).
- ✅ Миграции применяются чисто: `alembic upgrade head` проверен, дрейфа моделей нет.
- ✅ Сильные секреты сгенерированы (см. вывод сессии — вставь их ниже).

---

## 1. Секреты в боевом `.env`

Создай `.env` рядом с проектом и заполни. Сгенерированные мной значения (JWT/ENC/S3/WEBHOOK)
возьми из вывода `scripts` в сессии — **не переиспользуй из примеров в интернете**.

```dotenv
# --- режим ---
ENV=prod
BOT_MODE=webhook

# --- Telegram ---
BOT_TOKEN=                      # ⟵ ВПИШИ (токен от @BotFather)
WEBHOOK_BASE_URL=https://your.domain      # ⟵ ВПИШИ (боевой HTTPS-домен)
WEBHOOK_SECRET=                 # ⟵ вставь сгенерированный (или оставь пустым — выведется из BOT_TOKEN)
ADMIN_USER_IDS=                 # ⟵ ВПИШИ свой Telegram user_id (через запятую)

# --- админка (security) ---
ADMIN_JWT_SECRET=               # ⟵ вставь сгенерированный (НЕ дефолтный!)
ENC_SECRET=                     # ⟵ вставь сгенерированный (отдельный от JWT!)
ADMIN_IP_ALLOWLIST=             # (опц.) IP/через запятую — кто может заходить в админку

# --- инфра ---
DATABASE_URL=postgresql+asyncpg://USER:PASS@HOST:5432/DBNAME   # ⟵ ВПИШИ
REDIS_URL=redis://HOST:6379/0                                  # ⟵ ВПИШИ

# --- CORS (пункт 2) ---
CORS_ORIGINS=https://your.domain   # ⟵ ВПИШИ точный домен Mini App (НЕ *)

# --- объектное хранилище S3/MinIO (пункт 3) ---
S3_ENDPOINT=https://minio.your.domain   # ⟵ ВПИШИ (адрес MinIO/S3)
S3_KEY=                                  # ⟵ вставь сгенерированный (НЕ minioadmin!)
S3_SECRET=                               # ⟵ вставь сгенерированный (НЕ minioadmin!)
S3_BUCKET=aibot
S3_PUBLIC_URL=https://minio.your.domain/aibot   # ⟵ ВПИШИ (публичный URL бакета)

# --- платёжные шлюзы (включай только те, что используешь) ---
YOOKASSA_SHOP_ID=               # ⟵ ВПИШИ при использовании ЮКассы
YOOKASSA_SECRET=                # ⟵ ВПИШИ
STRIPE_SECRET=                  # ⟵ ВПИШИ при использовании Stripe
STRIPE_WEBHOOK_SECRET=          # ⟵ ВПИШИ (whsec_...)
CRYPTO_PAY_TOKEN=               # ⟵ ВПИШИ при использовании @CryptoBot
TRIBUTE_API_KEY=                # ⟵ ВПИШИ при использовании Tribute (СБП)
TRIBUTE_API_VERIFIED=false      # пункт 6 — ставь true ТОЛЬКО после сверки полей API

# --- AI чат через OmniRoute/LiteLLM (главный путь — см. §6.5) ---
AI_BASE_URL_ALLOWLIST=omniroute,litellm   # ОБЯЗАТЕЛЬНО для внутренних шлюзов (иначе SSRF-блок)
LITELLM_MASTER_KEY=             # ключ LiteLLM (если используешь litellm)

# --- AI-провайдеры напрямую (опционально, как фолбэк/альтернатива) ---
OPENAI_API_KEY=                 # (опц.) прямой ключ OpenAI
OPENROUTER_API_KEY=             # (опц.) единый шлюз-фолбэк
OPENROUTER_FREE_TIER=true       # false когда ключ оплачен и замаплены реальные модели
ANTHROPIC_API_KEY=              # (опц.)
GOOGLE_API_KEY=                 # (опц.)
```

Проверка, что дефолтов не осталось (должна пройти без ошибок):
```bash
python -c "from core.config import settings; print('secrets OK')"
```
Если увидишь `RuntimeError` про дефолтный JWT / пустой ENC_SECRET / minioadmin / CORS=* — конфиг
намеренно блокирует небезопасный запуск. Исправь и повтори.

---

## 2. CORS

Закрывается переменной `CORS_ORIGINS` выше — впиши **точный** домен Mini App.
`*` или пусто → приложение упадёт на старте (намеренная защита).

---

## 3. S3 / MinIO (мульти-реплика)

Без него загруженные файлы лежат на диске ОДНОЙ ноды и невидимы другим репликам/воркеру.
- Подними MinIO/S3, создай бакет `aibot`.
- Креды `S3_KEY`/`S3_SECRET` — вставь сгенерированные (root-креды MinIO `minioadmin`
  использовать НЕЛЬЗЯ, конфиг это блокирует).
- Сделай бакет (или префикс результатов) публично-читаемым, чтобы Telegram и провайдеры
  могли скачивать результаты по `S3_PUBLIC_URL`.

> Можно стартовать и на ОДНОЙ реплике без S3 (локальный диск-фолбэк уже есть). S3 нужен,
> когда масштабируешься на >1 реплику API/воркера.

---

## 4. Миграции на боевой БД

Цепочка миграций уже проверена (применяется до `head`, дрейфа нет).

**Авто-миграция (compose-стек):** делать вручную НЕ нужно — в `docker-compose.yml` есть
одноразовый сервис `migrate` (`alembic upgrade head`), от которого `bot`/`api`/`worker`/`beat`
зависят через `service_completed_successfully`. Ни один app-контейнер не стартует на схеме
ниже `head`. Alembic идемпотентен — повторный прогон без новых миграций безопасный no-op.
Это закрывает баг, из-за которого dev/rc-БД застряли на `0020`.

**Без compose** (запускаешь процессы вручную) — примени миграции сам перед стартом:
```bash
alembic upgrade head
```

---

## 5. Создать админа

```bash
python -m scripts.create_admin you@example.com 'СильныйПароль123' superadmin
```
Скрипт выведет `otpauth://...` — отсканируй в Google Authenticator / 1Password.
OTP потребуется при входе (для роли superadmin 2FA обязательна).

---

## 6. Интеграции и вебхуки

- **Telegram webhook** регистрируется при старте в webhook-режиме на
  `WEBHOOK_BASE_URL/webhook/telegram` (секрет — `effective_webhook_secret`). Проверь, что
  домен под HTTPS и доступен извне.
- **Шлюзы**: в кабинете каждого провайдера укажи URL вебхука:
  - ЮКасса → `https://your.domain/webhook/yookassa` (плюс их IP уже в allow-list по умолчанию)
  - Stripe → `https://your.domain/webhook/stripe` (скопируй `whsec_...` в `STRIPE_WEBHOOK_SECRET`)
  - CryptoBot → `https://your.domain/webhook/crypto`
  - Tribute → `https://your.domain/webhook/tribute`
- **Tribute**: ставь `TRIBUTE_API_VERIFIED=true` ТОЛЬКО после того, как сверишь реальные
  имена полей API/вебхука с их документацией (иначе шлюз намеренно инертен — деньги не двигает).
- Прогони тестовый платёж на минимальную сумму по каждому включённому шлюзу.

---

## 6.5. Чат через OmniRoute / LiteLLM (главный путь запуска)

Текстовый чат бота идёт через AI-аккаунт. Шлюзы OmniRoute и LiteLLM уже в
`docker-compose.yml` — приложение видит их внутри сети как `http://omniroute:20128/v1`
и `http://litellm:4000/v1`. Чтобы чат заработал:

1. **Открой allowlist для внутренних шлюзов** (ОБЯЗАТЕЛЬНО) — без этого SSRF-защита
   отклонит внутренний адрес с ошибкой «base_url resolves to a non-public address»:
   ```dotenv
   AI_BASE_URL_ALLOWLIST=omniroute,litellm
   ```
2. **Каталог моделей сидится сам** при деплое (сервис `migrate` →
   `scripts.seed_ai_models`): 9 текстовых моделей появятся в админке. Повторный деплой
   их не трогает (сид пропускается, если каталог не пуст). Сбросить к дефолту вручную:
   `docker compose run --rm migrate python -m scripts.seed_ai_models --force`.
3. **OmniRoute**: открой его дашборд (в проде — `omniroute.{$DOMAIN}` под IP-allowlist),
   подключи провайдера(ов) и создай в нём API-ключ. (LiteLLM: ключ — это
   `LITELLM_MASTER_KEY` из `.env`, провайдеры задаются в `litellm/config.yaml`.)
4. **Добавь аккаунт в админке**: AI-роутинг → новый аккаунт →
   `kind=omniroute`, `modality=text`, `base_url=http://omniroute:20128/v1`, вставь ключ.
   (Для LiteLLM: `kind=litellm`, `base_url=http://litellm:4000/v1`, ключ = master-key.)
5. **Проверь**: на карточке аккаунта нажми «Проверить» (онлайн-пинг), затем напиши боту —
   он должен ответить.

> Имена upstream-моделей засеяны в стиле OpenRouter (`openai/gpt-5.5`, …). Если твой
> шлюз отдаёт другие имена — поправь `upstream_model` каждой модели в админке (AI-роутинг).
> «Только чат» на старте: в админке Функции выключи «Генерация музыки» и «Генерация видео»
> (фото-сервисы уже выключены).

---

## 7. Провайдеры генерации

Сервисы без реального провайдера сейчас честно ВОЗВРАЩАЮТ деньги и выключены флагами:
`avatar`, `faceswap`, `upscale`, `recraft`. Когда подключишь провайдера:
1. Впиши его ключ в `.env` (`REPLICATE_API_KEY` и т.п.).
2. В админке (Features) включи соответствующий флаг.
3. Замени refund-заглушку в воркере на реальный вызов провайдера (см. TODO в
   `workers/avatar_tasks.py`, `workers/photo_tools_tasks.py`).

Текст/изображение/видео/музыка работают, как только задан хотя бы один AI-ключ.

---

## Финальная проверка перед «вкл»

```bash
python -m pytest -q          # 698 зелёных
ruff check .                 # чисто
python -c "from core.config import settings; print('config OK')"   # секреты не дефолтные
alembic upgrade head         # БД на последней версии
```
Затем: запусти API (gunicorn/uvicorn), бот (webhook), ARQ `WorkerSettings` (N реплик) и
ровно ОДИН `BeatSettings` (планировщик). Зайди в админку, проверь Dashboard/Health.
