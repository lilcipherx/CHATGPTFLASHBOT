# CHATGPTFLASHBOT — Финальный E2E-аудит (2026-07-06)

**Метод:** 12 параллельных доменных аудиторов (read-only), каждая находка — с `файл:строка` + дословной цитатой; все load-bearing HIGH/MEDIUM перепроверены лично по диску.
**Размер:** ~53k LOC Python (412 файлов), ~20k LOC TS/TSX (89), 41 миграция, 149 тест-файлов, 8 локалей.
**Итог:** дерево уже прошло много раундов закалки (`FIX:`-маркеры повсюду). **Нет CRITICAL.** 4 HIGH (+1 условный), ~24 MEDIUM, ~25 LOW. Старый `AUDIT_REPORT.md` (2026-07-02) полностью закрыт.

## Сводка по severity
| Severity | Кол-во | Ключевое |
|---|---|---|
| CRITICAL | 0 | — |
| HIGH | 4 (+1 условный) | ChannelPost NameError; обход лимита кредитов модератором; 2 таблицы без CASCADE FK (GDPR); блокирующий FK в 0037 |
| MEDIUM | ~24 | Suno null-URL/версия; YooKassa float+IP; packs-guard; невалидируемые admin-инпуты; мёртвые алерты; сырые i18n-ключи в ошибках Mini App |
| LOW | ~25 | RTL/BiDi полиш; недокументированные env; мелкие UX-нооп |

---

## HIGH

| # | Фича | Файл | Строка | Категория | Описание | Тип | Цитата | План фикса | Severity |
|---|---|---|---|---|---|---|---|---|---|
| H1 | Recovery канал-постов | workers/channel_tasks.py | 112 | Worker | `sweep_stuck_channel_posts` использует `ChannelPost`, но единственный импорт (стр.41) локален в `dispatch_channel_posts`; на модульном уровне символа нет → `NameError` на каждом тике (каждые 5 мин). Пост, застрявший в `sending` после SIGKILL/OOM, не восстанавливается никогда. | Баг/Обрыв цепочки | `update(ChannelPost).where(ChannelPost.status=="sending", ChannelPost.updated_at < cutoff)` | Добавить `from core.models.channel_post import ChannelPost` на верх модуля (как `Broadcast` в broadcast_tasks.py). | **HIGH** |
| H2 | Начисление кредитов | api/admin/users.py | 253 | Admin/Security | Эндпоинт `require_role("support")` (пускает и `moderator`, rank 2). Лимит срабатывает только `if admin.role == "support"` (точная строка) — модератор не «support» и не «admin+», значит начисляет **неограниченно** кредиты любому юзеру. | Уязвимость (RBAC/money) | `if admin.role == "support" and abs(req.amount) > SUPPORT_CREDIT_LIMIT:` | Проверять по рангу: `if ROLE_RANK[admin.role] < ROLE_RANK["admin"] and abs(req.amount) > SUPPORT_CREDIT_LIMIT: raise 403`. | **HIGH** |
| H3 | GDPR-эрейзер | core/models/billing.py + migrations/0038 | 155, 127 / 41-53 | DB/Compliance | `payment_methods.user_id` и `checkout_intents.user_id` объявлены как `mapped_column(BigInteger, index=True)` без `ForeignKey` и отсутствуют в `_CASCADE_FKS` (11 таблиц) → при удалении User сохранённые платёжные токены и checkout-интенты остаются сиротами, `delete_user_data()` их не каскадит (GDPR Art.17). | Обрыв цепочки/Compliance | `user_id: Mapped[int] = mapped_column(BigInteger, index=True)` | Новая миграция (паттерн 0038 `NOT VALID`→`VALIDATE`): FK `users.user_id ondelete=CASCADE` + добавить обе таблицы в каскадный delete; добавить `ForeignKey` в модели. | **HIGH** |
| H4 | Деплой-миграция | migrations/0037_round5_schema_fixes.py | 102 | DB | FK `users.bot_id → bot_instances` добавляется обычным `op.create_foreign_key` → валидирующий скан под ACCESS EXCLUSIVE на горячей `users` блокирует все чтения/записи на время скана (в отличие от корректного `NOT VALID`→`VALIDATE` в 0038). | Perf/Config | `op.create_foreign_key("users_bot_id_fkey","users","bot_instances",["bot_id"],["id"],ondelete="SET NULL")` | Добавлять `NOT VALID` в `autocommit_block`, затем отдельный `VALIDATE CONSTRAINT`. (Правка старой миграции нежелательна — вынести в новую ремонтную миграцию или задокументировать maintenance-window.) | **HIGH** |
| H5* | Cross-origin Mini App | miniapp/index.html | 17 | UI/Config | `connect-src` не содержит origin API. При split-origin деплое (`VITE_API_BASE=https://api...`) все `/api`-фетчи блокируются CSP → кредиты «—», гриды в ошибке, генерация невозможна. Same-origin (Caddy) — не воспроизводится. | Config баг (условный) | `connect-src 'self' https://api.telegram.org https://api.openai.com ...` | Для same-origin — без изменений (задокументировано AUDIT-M16). Для split-origin — подставлять API-origin в CSP на этапе сборки. | **HIGH*** (только split-origin) |

---

## MEDIUM

| # | Фича | Файл | Строка | Категория | Описание | Тип | Цитата | План фикса | Severity |
|---|---|---|---|---|---|---|---|---|---|
| M1 | Suno выдача | core/ai_router/music_adapters.py | 85, 93 | Integration | Poll возвращает `complete` с `result_url=None`, если `audio_url` отсутствует/переименован (Kling так не делает — там `raise`). Воркер «доставляет» None: юзер списан за трек, которого нет, без рефанда. | Баг (money leak) | `return JobStatus("complete", result_url=body.get("audio_url"))` | Возвращать `complete` только если URL truthy, иначе `processing`/`failed` — в обеих ветках. | MEDIUM |
| M2 | Suno версия | core/ai_router/music_adapters.py | 40 | Integration | UI во всех локалях рекламирует «Suno V5.5», адаптер по умолчанию шлёт `suno-v4` (спеки не задают `model`). Юзер платит за V5.5, получает v4. | Баг | `"model": params.get("model") or "suno-v4"` | Прокинуть реальный id V5.5 или синхронизировать лейбл. | MEDIUM |
| M3 | Пустой ответ LLM | core/ai_router/openai_adapter.py (+anthropic/google) | 53 | Integration | Пустой/зарезанный safety-фильтром ответ → `text=""` с дефолтным `ok=True` → вызывающий списывает квоту и не рефандит. | Баг (money leak) | `choice = (getattr(msg,"content",None) or "") if msg else ""` | При пустом тексте возвращать `TextResult(..., ok=False)` (или raise) — рефанд по контракту `ok`. | MEDIUM |
| M4 | YooKassa сумма | core/payments/yookassa_gw.py | 218 | Payment | Авторитетная сумма парсится через `float` перед minor-units → возможен off-by-one копейка на непредставимых значениях (единственный money-путь на `float`; crypto уже на `Decimal`). | Баг | `amount_rub = float(amount_obj.value)` | `int((Decimal(str(amount_obj.value))*100).to_integral_value())` (как crypto_gw). | MEDIUM |
| M5 | YooKassa webhook IP | api/routers/webhooks.py | 115 | Security | IP-allowlist берёт `request.client.host` = сокет-пир (за прокси это IP прокси), XFF не читается → либо все вебхуки отклоняются, либо allowlist бессмыслен. (Не форжинг: сумма ре-фетчится из API.) | Config | `client_ip = request.client.host if request.client else ""` | Брать правый недоверенный хоп XFF с trusted-proxy count, или терминировать allowlist на прокси. | MEDIUM |
| M6 | packs deduct | core/services/packs.py | 64 | Security/Validation | У `try_consume` нет `if amount<=0: return False` (у sibling `credits.try_consume` есть, AUDIT-9). При negative amount `balance < amount` = False → вычитание отрицательного = **начисление** пачки. | Уязвимость (money) | `if row is None or getattr(row, field) < amount: return False` | Добавить `if amount <= 0: return False` в начало (+ в `refund`). | MEDIUM |
| M7 | Broadcast кнопка | api/admin/ops.py | 944 | Security/Validation | `button_url` не проверяется на схему (в отличие от `channel.py`/`banners.py`), рендерится в `InlineKeyboardButton(url=...)` для всей базы. `javascript:`/`data:` уходит всем. | Validation | `"button_url": (req.button_url or "").strip() or None` | Прогнать через тот же `_validate_button_url`. | MEDIUM |
| M8 | Начисление сумм | api/admin/users.py | 239 | Validation | `CreditsRequest.amount: int` без `ge/le` → до 2⁶³ кредитов одним вызовом (для admin+ и, через H2, модератора). | Validation | `amount: int        # may be negative to deduct` | `amount: int = Field(..., ge=-1_000_000, le=1_000_000)`. | MEDIUM |
| M9 | Broadcast/DM текст | api/admin/ops.py; api/admin/messaging.py | 835; 35 | Validation | `text: str` без `max_length` → многомегабайтное тело в БД/очередь всем, потом Telegram-send падает (>4096) — тихий провал кампании. | Validation | `text: str` | `text: str = Field(..., max_length=4096)` в обеих моделях. | MEDIUM |
| M10 | Banner/Effect поля | api/admin/banners.py; api/admin/effects.py | 96; 124 | Validation | `title/subtitle/image_url/prompt_template` без `max_length` — показываются каждому юзеру Mini App, безразмерные строки в витрине. | Validation | `title: str \| None = None` | Добавить `Field(max_length=...)` (title 200, subtitle 500, url 2048, prompt 4000). | MEDIUM |
| M11 | Promo награда | api/admin/ops.py | 1225 | Validation | `reward_amount` без `le` (для `premium` = дни → бессрочная подписка; для credits — безразмерный минт); `code` без `max_length`. | Validation | `reward_amount: int` | `Field(0, ge=0, le=…)`, `max_uses ge=1 le=…`, `code max_length=64`. | MEDIUM |
| M12 | Логин-токены | api/admin/auth.py | 201 | Security | `/auth/login` возвращает полные access+refresh JWT в теле (`/auth/refresh` уже отдаёт пустые, FINAL-6) → при XSS токены эксфильтруются, обходя httpOnly. | Уязвимость | `access_token=access, refresh_token=refresh_tok,` | Зеркалить FINAL-6: пустые токены в теле для браузера, тело-токены только за явным non-browser флагом. | MEDIUM |
| M13 | Мёртвые алерты | monitoring/alerts.yml | 88, 96, 104 | Infra | `aibot_http_requests_total`, `aibot_payments_failed_total`, `aibot_ai_provider_429_total` нигде не эмитятся → Api5xxSpike/PaymentFailureSpike/AIProvider429Spike никогда не срабатывают (именно кейсы 5xx-шторм/сбой платежей/429). | Config/Monitoring | `expr: sum(increase(aibot_payments_failed_total[15m])) > 10` | Эмитить счётчики из приложения (HTTP-middleware, payments-hook, ai-router-hook) в `/metrics`, либо закомментировать правила. | MEDIUM |
| M14 | Staging boot | .env.staging.example | 25 | Config | `CORS_ORIGINS=*` при `ENV=staging`: `_require_prod_secret` рано выходит только для dev/test, staging проходит прод-гейт и падает на `if "*" in cors...: raise`. Стек не стартует. | Config | `CORS_ORIGINS=*` | Указать реальный origin staging. | MEDIUM |
| M15 | Prometheus scrape | monitoring/prometheus.yml | 26 | Infra | На публичном деплое `/metrics` требует METRICS_TOKEN (403 без него), но токен в скрейпе закомментирован и env не раскрывается → `aibot_*` не собираются, ApiDown/GenerationBacklog не срабатывают. | Config | `# params:\n#   token: [...]` | Инжектить токен на деплое; фейлить деплой при отсутствии. | MEDIUM |
| M16 | Ошибки Mini App | miniapp/src/api/client.ts + CreateSheet.tsx/Create.tsx/Profile.tsx | 44 / 159,76 / 339,179 / 63 | UI/i18n | client бросает `Error` с **i18n-ключом** как message (`err_server`...). В 3+ местах он рендерится сырым: юзер видит `err_server` / `Error: err_generic` вместо перевода при 500/429/expired-auth. | UI-UX баг | `throw new Error(m[c] || "err_generic")` → `setError(msg)` | Переводить на границе: `setError(t(msg))`, `setError(t(e.message))`. | MEDIUM |
| M17 | Carousel язык | miniapp/src/components/Carousel.tsx | 27 | UI/i18n | Баннеры фетчатся один раз на mount (`deps []`), не подписаны на `onLangChange`. После `syncLang` из `/profile` (юзер сменил язык `/language`) заголовки/картинки баннеров остаются на старом языке навсегда. | UI-UX баг | `useEffect(() => { api.banners()... }, [])` | Подписаться на `onLangChange` и рефетчить, либо ключевать эффект по `getLang()`. | MEDIUM |
| M18 | Профиль-ошибка | miniapp/src/App.tsx | 91 | UI | Хорошо обработан только `err_auth`; при `err_server`/`err_rate`/timeout ни один гейт не срабатывает — приложение рендерится с кредитами «—» и без retry на Home/Trends/Create (retry только в Profile). | UI-UX баг | `{profile?.credits ?? "—"} ✨` | App-level error+retry для любого `profileError`, либо сделать chip кредитов тапабельным → `reloadProfile()`. | MEDIUM |
| M19 | Localization race | admin/src/pages/Localization.tsx | 109 | Admin | `load()` без `useLatestGuard` (все прочие списки — с ним). Быстрое переключение `<Select>` локали → медленный ранний ответ перезаписывает `items` не тем языком. | Race Condition | `const data = await apiL.get(loc); setLocales(...); setItems(...)` | Захватить `isLatest=guard()` до `apiL.get` и гейтить `setItems`. | MEDIUM |
| M20 | RTL раскладка | miniapp/src/styles.css | 254 (+233,267,338,501,509,586) | i18n/Font | `dir=rtl` ставится, но ~13 физических left/right свойств (бейджи, `.photo-x`, стрелки карусели, cost-badge) не зеркалятся под RTL → в арабском контролы прижаты к LTR-стороне и накладываются. | UI-UX баг | `position: absolute; right: 8px; top: 8px;` | Логические свойства (`inset-inline-end/start`, `text-align:start/end`) или `[dir=rtl]`-оверрайды. | MEDIUM |
| M21 | BiDi изоляция | miniapp/src/i18n.ts | 377 | i18n | Интерполируемые LTR-значения (числа, `{name}`, `@handle`) вставляются в RTL-строки без BiDi-изоляции (нет `<bdi>`/`⁨..⁩`) → в арабском порядок символов может ломаться у пунктуации/хэндлов. | UI-UX баг | `s = s.replaceAll(`{${k}}`, String(v)...)` | Оборачивать значения в `⁨`+v+`⁩` или `<bdi>` в компонентах. | MEDIUM |
| M22 | GDPR-экспорт | bot/handlers/account.py / core/services/gdpr.py | 132 / — | Compliance | Art.17 (удаление) реализован, но нет self-service экспорта данных (Art.20) — экспорт только admin-side CSV, юзер его вызвать не может. | Compliance | `@router.message(Command("delete_account"))` | Добавить `/export_data` (бот/Mini App), отдающий свои записи (профиль/транзакции/usage/генерации) JSON/CSV. | MEDIUM |
| M23 | SSRF rehost | core/services/storage.py | 271 | Security | `follow_redirects=True`: httpx сам ходит по цепочке до финальной проверки → промежуточный `302→169.254.169.254` уже фетчится; плюс DNS-rebinding TOCTOU (host резолвится дважды). Досягаемость ограничена (кормится URL-ами провайдеров, не юзера). | Уязвимость (needs-verify) | `httpx.AsyncClient(follow_redirects=True)` | `follow_redirects=False` + ре-валидация каждого хопа, либо pin resolved IP (validate-then-connect). | MEDIUM |
| M24 | Non-concurrent индекс | migrations/0004_user_indexes.py | 36 | DB | `CREATE INDEX ix_users_is_banned` на горячей `users` без `CONCURRENTLY`/`autocommit_block` → SHARE-lock блокирует записи на время сборки (backfill-путь на существующих БД). | Perf | `op.create_index("ix_users_is_banned","users",["is_banned"], postgresql_where=...)` | Обернуть в `autocommit_block()` + `postgresql_concurrently=True`. | MEDIUM |

---

## LOW (сводно)

| # | Файл:строка | Описание | Тип |
|---|---|---|---|
| L1 | core/ai_router/image_adapters.py:127 | `for d in resp.data` без guard → `TypeError` при `data=None` (не `ProviderUnavailable`). | Баг |
| L2 | core/ai_router/google_adapter.py:38 | Плоский prompt `f"{role}: {content}"` → возможен role-spoofing (сам system-prompt изолирован). | Уязвимость |
| L3 | core/ai_router/registry.py:210 | На transient 5xx `mark_error` в цикле ретраев → инфляция `total_errors`. | Perf |
| L4 | core/ai_router/gateways.py:198,135 | `data.get(...)` без `isinstance(list)` (Muapi/Kie) — как уже пофикшено для Suno (AI-17). | Баг |
| L5 | core/payments/tribute_gw.py:6 | Tribute UNVERIFIED (само-загейчен; деньги не двигает, пока `TRIBUTE_API_VERIFIED` не выставлен). | Config |
| L6 | bot/handlers/premium.py:248 | Stars `total_amount`/`payload` пишутся в леджер без ре-валидации против прайса (источник доверенный/серверный). | Validation |
| L7 | core/services/credits.py:47 | `grant` без sign-guard (`max(0,...)` только полит по нулю; negative прошёл бы как дебет). Все вызовы клампят — защитно. | Validation |
| L8 | core/services/throttle_config.py:55 | Кэш `cache:throttle_config` не инвалидируется на запись (только TTL 30s; admin-writer пока не подключён). | Config |
| L9 | core/services/billing.py:292 | `notify_purchase_bonus` смотрит только новейший лог → второй быстрый бонус может не получить DM (кредиты начислены). | Баг |
| L10 | core/services/retention.py:46 | `prune_jobs/prune_gallery` материализуют все URL в один список (безлимитно) на первом прогоне большого бэклога. | Perf |
| L11 | bot/handlers/account.py:138 | Промпт удаления советует `/cancel`, но хэндлера `Command("cancel")` нет. | Заглушка |
| L12 | bot/handlers/promo.py:41 | `/promo` без выделенного per-user лимитера попыток (только глобальный throttle). | Валидация |
| L13 | bot/handlers/photo.py:201 | Кнопка «Photo Effects» (`photoeffects`) падает в generic «coming soon» (video-аналог даёт hint). | Мёртвый код |
| L14 | bot/handlers/photo.py:490 | State-scoped `img:more`/`pcfg:`/`vcfg:` не отвечают на старых сообщениях → кнопка «крутится». | UI-UX баг |
| L15 | bot/middlewares/throttle.py:47 | `pre_checkout_query` дропается при троттле без `answer()` → редкий тихий провал оплаты. | Баг |
| L16 | api/admin/ops.py:1031 и др. | Read-эндпоинты возвращают голый массив без `{total,limit,offset}` → UI не строит пагинатор. | Pagination |
| L17 | api/admin/crm.py:54 | `add_note`/`add_tag` не проверяют существование user → 500 на FK-нарушении. | Data integrity |
| L18 | api/admin/auth.py:107 | `password` без `max_length` на pre-auth пути → лишняя argon2-нагрузка (митигировано rate-limit). | Validation |
| L19 | admin/src/pages/Maintenance.tsx:127 | Дублирующий `useEffect(load)` → двойной фетч на mount. | Мёртвый код |
| L20 | admin/src/pages/Promos.tsx:415 | Награда `amount == 0` допускается (no-op промокод). | Validation |
| L21 | miniapp/src/api/client.ts:52 | `signal` в `uploadEffect` принят, но ни один caller не передаёт → мёртвый параметр, upload не отменяется на unmount. | Мёртвый код |
| L22 | miniapp/src/pages/History.tsx:44 | Retry не сбрасывает `items` в null → мелькает ложное «empty» вместо спиннера. | UI-UX баг |
| L23 | miniapp/src/api/client.ts:255 | `category`/`kind`/`trending` в query без `encodeURIComponent` (значения из фикс-списка). | Validation |
| L24 | Caddyfile:4 | Нет CSP-заголовка на прокси (HSTS/nosniff/XFO/Referrer есть). | Security |
| L25 | docker-compose.prod.yml:27+ | Нет resource limits на pgbouncer/litellm/minio/caddy/backup (litellm может OOM). | Config |
| L26 | .dockerignore:20 | В образ едут `miniapp/`/`admin/`/`tests/`/`loadtests/` (не секреты — bloat). | Config |
| L27 | .env.example | Не задокументированы ~15 tunables (REPORT_CHAT_ID, STUCK_JOB_MINUTES, AI_*_TIMEOUT, ...). | Docs |
| L28 | core/i18n/locales/es.py:160 и др. | Горстка непереведённых слов («POPULAR»/«Editor»/«Guide») в es/fr/pt (большинство — бренд-токены). | i18n |
| L29 | core/models/*.py | Отсутствующие FK: `contest_entries.contest_id`, `gifts.buyer_id/redeemed_by`, `admin_id` в audit/broadcast/notes. | Data integrity |
| L30 | migrations/0022,0037 | `int4→int8` rewrites под ACCESS EXCLUSIVE (корректность, нужен maintenance-window). | Perf |

\* — большинство LOW защитные/полишевые; ни один не ломает деньги/не крашит хэндлер.

---

## Что подтверждено ЧИСТЫМ (не перепроверять как баги)
Подписи вебхуков (все через `hmac.compare_digest`), idempotency по unique `gateway_tx_id`, sync-SDK в `asyncio.to_thread`, row-locks на всех балансах, refund-on-failure, moderation-before-charge, conditional-UPDATE claim на мутирующих кронах, MultiBotKeyBuilder изоляция FSM, argon2id + анти-энумерация + JWT token_version + TOTP/API-ключи под Fernet, RBAC на всех ~170 admin-эндпоинтах, санитизация ключей в `last_error`, CSV-экспорт с row-cap, XSS-санитайзер в admin, i18n parity (301 core / 120 miniapp ключей × 8 локалей идентичны), 0 skip/xfail в тестах, GDPR delete-cascade, presigned TTL + magic-byte MIME + path-traversal guard.

---

## Порядок исправления (после одобрения)
CRITICAL → HIGH → MEDIUM → LOW. Правки money/auth/webhook/AI соблюдают «Verified Hardening» из CLAUDE.md; схема — новой миграцией (`CONCURRENTLY`/`NOT VALID→VALIDATE`); каждый фикс тегируется `FIX: AUDIT13-*` / `AI-24+`. Верификация: `pytest tests/`, `tsc --noEmit` + `npm run build` (miniapp+admin), валидация compose.
