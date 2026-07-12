# Production Checklist — CHATGPTFLASHBOT

Ручной чеклист для staging/prod. Статус на 2026-07-12, `main` = `58c11a4`,
AWS live = deployed из `main` (code SHA `2ea538d`, + docs).

## Locally verified ✅ (доказано в этой сессии)
- [x] `ruff check .` — чисто (гейт CI).
- [x] Pytest — 886 passed; coverage 68% (ratchet поднят 50→65).
- [x] Frontend: `miniapp` + `admin` — `npm ci && tsc --noEmit && build`; Playwright e2e (miniapp).
- [x] `bandit -r core api bot workers -ll` — 0.
- [x] `alembic upgrade head` на чистой БД + `scripts.check_migrations` — drift нет; heads = `0042_search_model`.
- [x] Платежи/рефанды: идемпотентность, `successful_payment` carve-out в middleware, атомарный charge.
- [x] Auth/RBAC: backend-authz отдельно от frontend-guard, ownership/IDOR-проверки.
- [x] Генерация/квоты: атомарный charge/refund, rate-limit gallery submit + ownership.
- [x] SSRF/upload hardening: streaming size-cap, Pillow decompression-bomb guard, per-hop re-validation.
- [x] `/metrics` закрыт на edge (Caddy → 403) + auth в приложении.

## Deployed & verified on AWS ✅
- [x] Controlled deploy выполнен (pre-gate: backup checksum OK, rollback-теги, снапшот каталога).
- [x] Post-deploy: api `healthy`, `/health=200`, `/health/ready=200`, public `/health=200`, `/metrics=403`, `/miniapp/=200`.
- [x] `alembic current` = `0042` (без изменений схемы); restarts=0; error-scan пусто.
- [x] SHA-эквивалентность local = GitHub = AWS.
- [x] `beat` = 1 реплика.

## Requires production operational verification (только владелец) ⚠️
- [ ] **[P0-если-открыт] AWS Security Group** инстанса `ip-172-31-45-10`: Inbound публично только `80`,`443`; `22` — с owner-IP. Портов `5432/6379/9000/9001/20128/8000` в `0.0.0.0/0` быть НЕ должно. (`ports: []` в prod-оверлее их не закрывает — защита только на SG; `ufw` inactive.)
- [ ] `.env` на сервере: `ENV=production`, `DEV_WEBAPP_BYPASS` выключен, `CORS_ORIGINS` без `*`, `ADMIN_ALLOW_IP` корректен. Права `.env` ужать с `0755` до `0600`.
- [ ] Восстановить GitHub Actions (billing/минуты) — вернуть CI-гейт; после этого важные изменения через PR + зелёный CI.
- [ ] Убрать rollback-снапшот `CHATGPTFLASHBOT.predeploy.20260712-121634` и `:rollback-*` теги после подтверждения стабильности (диск 62%).

## Requires staging (платные/внешние, не выполнялось) 🧪
- [ ] Реальные YooKassa webhook + refund end-to-end.
- [ ] Платные AI-генерации (chat/vision/image/video/music/TTS/STT) через реальных провайдеров.
- [ ] Реальный Telegram webhook flow + Mini App initData от настоящего клиента.

## Rollback runbook
1. `cp -a /home/ubuntu/CHATGPTFLASHBOT.predeploy.<ts>/. /home/ubuntu/CHATGPTFLASHBOT/`
2. `for s in api bot worker beat migrate; do docker tag chatgptflashbot-$s:rollback-<ts> chatgptflashbot-$s:latest; done`
3. `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate`
4. Крайний рубеж (только при повреждении данных, вручную): восстановление из `/backups/aiobot-<ts>.sql.gz` (checksum-verified).
