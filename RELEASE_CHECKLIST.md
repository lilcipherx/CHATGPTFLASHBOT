# Release Checklist — ChatGPTFlashBot

Финальный **go/no-go** перед выкаткой в прод. Это НЕ инструкция по деплою — она ссылается
на уже существующие доки:
- Деплой/инфра — [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md), `docker-compose.prod.yml`
- Операционка/инциденты — [`docs/RUNBOOK.md`](docs/RUNBOOK.md), [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md)
- Ручные сценарии — [`MANUAL_TESTS.md`](MANUAL_TESTS.md)
- Мониторинг — [`docs/MONITORING.md`](docs/MONITORING.md), `docker-compose.monitoring.yml`
- Бэкап/восстановление — [`docs/BACKUP.md`](docs/BACKUP.md), [`docs/RESTORE.md`](docs/RESTORE.md)
- Переменные окружения — [`docs/ENV.md`](docs/ENV.md)
- Известные ограничения — [`ISSUES.md`](ISSUES.md)

Текущее состояние: ветка `chore/production-hardening`, head миграции **`0028_banner_locale`**
(единственный head). Backend 663 tests / ruff clean; miniapp+admin tsc+vitest green.

---

## A. Pre-flight — уже зелёное (проверяемо в CI/локально)
- [x] `python -m pytest -q` → 663 passed
- [x] `ruff check .` → clean (блокирующий гейт CI)
- [x] miniapp: `npx tsc -b` + `npx vitest run` green
- [x] admin: `npx tsc -b` + `npx vitest run` green
- [x] `alembic heads` → один head (`0028_banner_locale`), цепочка линейна
- [x] Полная локализация (8 языков), паритет плейсхолдеров
- [x] Security-ревью дельты: уязвимостей нет; LIKE-escape + дедуп счётчиков применены
- [x] Денежный путь (вебхуки/шлюзы/`apply_event`/`refund_job`): идемпотентность и
      корректность рефандов подтверждены кодом + тестами

## B. Перед мержем
- [ ] Push ветки + PR в `main`, прохождение CI (lint + tests + migration-drift)
- [ ] Ревью PR человеком
- [ ] `.env` прод заполнен по [`docs/ENV.md`](docs/ENV.md); секреты НЕ в гите
- [ ] `BOT_MODE` выбран осознанно: `webhook` для прода (требует `webhook_base_url` + TLS),
      `polling` только для одного инстанса. Не запускать ДВА getUpdates-консьюмера на один токен.

## C. Гейт — staging-smoke на РЕАЛЬНОЙ инфре (Postgres + Redis + Docker + Caddy/TLS)
> Это нельзя проверить в dev-окружении (SQLite + fakeredis). Обязательный ручной прогон.
- [ ] `alembic upgrade head` на боевом Postgres → ревизия `0028_banner_locale`, без ошибок
- [ ] `GET /health/ready` → 200 (`database: true`, `redis: true`)
- [ ] `GET /health/providers` → ожидаемые провайдеры detected
- [ ] `GET /metrics` → валидный Prometheus; Grafana/Loki поднимаются (`docker-compose.monitoring.yml`)
- [ ] Обе SPA отдаются: `/` (Mini App) и `/admin/` → 200
- [ ] Админка fail-closed: `/api/admin/*` без токена → 401/403; вход + 2FA работают
- [ ] Все Mini App эндпоинты initData-gated (forged initData → 401)
- [ ] Telegram-вебхук (если `BOT_MODE=webhook`) принимает подписанный апдейт, отвергает forged (403)
- [ ] Caddy: XFF перезаписывается, `/api/admin/*` снаружи закрыт, IP-allowlist работает

## D. Live-ключи — то, что «по коду верно», но не проверено вживую
- [ ] **Платежи** — один реальный платёж КАЖДЫМ способом, проверить зачисление + идемпотентность дубля вебхука:
  - [ ] Telegram Stars (`successful_payment`)
  - [ ] YooKassa (СБП)
  - [ ] Stripe
  - [ ] CryptoBot
  - [ ] Tribute
- [ ] **Возврат**: спровоцировать неуспешную генерацию → убедиться, что списание вернулось (кредиты/пак/Stars)
- [ ] **Генерация** на боевых ключах — по одному прогону на класс: image, video, music; доставка результата
- [ ] **AI-чат**: проверить text-chat генерацию (см. [[ISSUES.md]] — в dev-БД роутинг был нерабочим; подтвердить на проде)
- [ ] **Авто-renew Premium**: сохранённый способ оплаты списывается off-session (Stripe/YooKassa)

## E. Живой проход UX
- [ ] Бот: `/start` (+ deep-link `ref_`, `promo_`, `redeem_`), меню `/photo` `/video`, оплата пакета, бонус, рефералка
- [ ] Mini App в Telegram: карусель (картинки из админки рендерятся), эффекты, история, профиль, оплата
- [ ] Хотя бы на 2 языках кроме RU — убедиться, что нет утечек русского

## F. Осознанные остаточные ограничения (НЕ блокеры, зафиксировать в release notes)
- [ ] White-label multi-bot: Mini App initData проверяется только против основного `bot_token`
- [ ] Streaming AI обходит внутренний учёт трат (`spend_micros`); квота пользователя списывается корректно
- [ ] `/metrics` делает несколько `COUNT(*)` за scrape — следить на 1M+ строк (интервал scrape / reltuples)
- [ ] SQLite FK enforcement off (dev/test only; Postgres обеспечивает нативно)

## G. Rollback / страховка
- [ ] Бэкап БД снят ДО миграции (см. [`docs/BACKUP.md`](docs/BACKUP.md))
- [ ] План отката миграции проверен (`alembic downgrade -1` на staging-копии)
- [ ] Алерты подняты (ошибки/латентность/health) — [`docs/MONITORING.md`](docs/MONITORING.md)

---

**Go-критерий:** A+B зелёные, C полностью пройден на staging, D хотя бы по одному успешному
кейсу на каждый шлюз/класс генерации, E пройден вживую, F зафиксирован в release notes, G готов.
