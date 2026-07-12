# AWS Production Inventory — read-only discovery (Phase 11a)

Собрано `ssh flashbot`, **только чтение**, значения секретов не выводились.
Дата сбора: 2026-07-12 (~07:05–07:10 UTC).

## Хост / окружение
- EC2 instance user/host: `ubuntu@ip-172-31-45-10` (приватный IP 172.31.45.10).
- OS: Ubuntu 24.04, kernel `6.17.0-1019-aws`, x86_64.
- Uptime: ~5 дней; load avg низкий (0.04/0.12/0.10).
- Docker `29.1.3`, Docker Compose `v2.40.3`.
- Диск `/`: 29G, занято 18G (62%), свободно 11G.
- RAM: 15Gi всего, ~2.6Gi used, ~12Gi available (≈ t3.xlarge/большой инстанс).
- `aws` CLI: **отсутствует** на хосте.

## Deploy-путь и механизм
- Активный каталог: `/home/ubuntu/CHATGPTFLASHBOT` — **НЕ git-репозиторий** (`.git` отсутствует).
- Рядом backup-копия каталога: `/home/ubuntu/CHATGPTFLASHBOT.old.20260707-053733` → выкатка = замена каталога (swap), не `git pull`.
- Механизм получения кода по DEPLOY_AWS.md: `git clone https://<PAT>@github.com/...` (приватный репо, нужен PAT) — но на текущем каталоге git снят.
- Файлы кода датированы 2026-07-07; `admin/` — 07-07 14:27; `Caddyfile` — 07-07 20:38 (правился вручную, есть `Caddyfile.bak.1783456749`).

## Compose / контейнеры (все Up)
Проект `chatgptflashbot`, config: `docker-compose.yml` + `docker-compose.prod.yml`.

| Сервис | Образ | Статус | Порты (host) |
|---|---|---|---|
| api | chatgptflashbot-api:latest (`c43c458ccaad`) | Up 4d (healthy) | 0.0.0.0:8000 |
| bot | chatgptflashbot-bot:latest (`e2cad793f086`) | Up 4d | — |
| worker | chatgptflashbot-worker:latest (`47134a7c13ad`) | Up 4d | — |
| beat | chatgptflashbot-beat:latest (`60f9361cb922`) | Up 4d | — (1 реплика ✅) |
| caddy | caddy:2-alpine (`5f5c8640aae0`) | Up 4d | 0.0.0.0:80, :443 |
| postgres | postgres:16-alpine (`e013e867e712`) | Up 5d (healthy) | **0.0.0.0:5432** |
| pgbouncer | edoburu/pgbouncer:latest (`4c1ca296ef52`) | Up 5d | 5432/tcp (internal) |
| redis | redis:7-alpine (`6ab0b6e73817`) | Up 5d (healthy) | **0.0.0.0:6379** |
| minio | minio/minio:latest (`14cea493d9a3`) | Up 5d | **0.0.0.0:9000-9001** |
| omniroute | diegosouzapw/omniroute:latest (`ceae8d9da0ac`) | Up 5d (healthy) | **0.0.0.0:20128** |
| backup | postgres:16-alpine | Up 5d | 5432/tcp (internal) |
| migrate | chatgptflashbot-migrate:latest (`123897ebae5b`) | (one-shot) | — |

Внешние образы на `latest` (postgres/redis/caddy/minio/omniroute/pgbouncer) — не digest-pinned.

## БД / миграции
- `alembic current` (в БД) = `0042_search_model (head)`.
- `alembic heads` (код на сервере) = `0042_search_model`.
- Репо `origin/main` (после merge PR #1) migration heads = `0042_search_model`.
- **Вывод: новых миграций нет — деплой из main будет code-only, схема БД не меняется.**

## Бэкапы (rollback-основа)
- Volume `chatgptflashbot_backups` → `/backups` в backup-контейнере; скрипт bind `scripts/backup.sh`.
- Ежедневная ротация с checksum: `aiobot-YYYYMMDD-HHMMSS.sql.gz` + `.sql.gz.sha256`.
- Присутствуют 07-08…07-12. **Свежий: `aiobot-20260712-065027.sql.gz` (+ .sha256)**, ~15 мин до проверки.
- Размер gzip ~12K (маленькая БД / мало пользовательских данных).

## Сеть / firewall
- `ufw`: **inactive** (хостового firewall нет).
- Слушают на `0.0.0.0`: 22, 80, 443, 8000, 5432, 6379, 9000, 9001, 20128.
- Единственная защита внутренних портов (5432/6379/9000/9001/20128/8000) — **AWS Security Group**, которую из хоста проверить нельзя (нет aws CLI/креды).

## Секреты окружения (наличие, БЕЗ значений)
`.env` присутствует (права `0755` — избыточно открытые). Имена переменных:
`ADMIN_ALLOW_IP, ADMIN_IP_ALLOWLIST, ADMIN_JWT_SECRET, ALERT_BOT_TOKEN, ALERT_CHAT_ID,
BOT_MODE, BOT_TOKEN, CORS_ORIGINS, DATABASE_URL, DEV_WEBAPP_BYPASS, DOMAIN, ENC_SECRET,
ENV, GRAFANA_ADMIN_PASSWORD, LITELLM_MASTER_KEY, LOG_LEVEL, METRICS_TOKEN,
MFA_REQUIRED_ROLES, MINIAPP_URL, OPENAI_BASE_URL, POSTGRES_PASSWORD, REDIS_URL,
S3_BUCKET, S3_ENDPOINT, S3_KEY, S3_SECRET, WEBHOOK_BASE_URL, YOOKASSA_TAX_SYSTEM_CODE`.

Проверить значения (не выводя их): `ENV=production`, `DEV_WEBAPP_BYPASS` выключен, `CORS_ORIGINS` без `*`, `ADMIN_ALLOW_IP` корректен.

## Caddyfile
- Серверный `Caddyfile` sha256 `1431e2c2…` ≠ репо `origin/main` sha256 `def9093b…`.
- На сервере ручные правки (есть `.bak`); при деплое каталога заменится на hardened-версию из main
  (admin-IP restrict, `header_up X-Forwarded-For {remote_host}`, `/metrics` → 403, CSP для admin/miniapp).
- Требует `--force-recreate caddy` (инвариант проекта).

## Открытые вопросы / риски (требуют владельца или prod-верификации)
1. **[P0? — requires production verification]** AWS Security Group: убедиться, что 5432/6379/9000/9001/20128/8000 закрыты извне (публично только 22 из owner-IP, 80/443). `ports: []` в prod-оверлее НЕ закрывает базовые порты (Compose складывает списки `ports`), поэтому фактическая защита — только SG.
2. **[transfer]** Нет git на сервере → для выкатки main нужен PAT (секрет, которого нет) ИЛИ `rsync` локального дерева.
3. **[config]** Серверный `Caddyfile`/`.env` — untracked; деплой каталога не должен затирать `.env` и volume-данные.
4. **Supply chain:** внешние образы и app-образы не pinned по digest; Actions на аккаунте не запускаются (billing) — CI-гейт недоступен.

---

## Phase 11b–11e — Controlled deploy EXECUTED (2026-07-12)

**Метод:** нет git на сервере → доставка `git archive` (LF, `core.autocrlf=false`) + собранные
`miniapp/dist`+`admin/dist`, tar-over-ssh с checksum-верификацией, распаковка поверх (без `--delete`),
`.env`/volumes не тронуты. Деплой **code-only** (миграций нет).

**Pre-deploy gate:**
- Свежий бэкап checksum-verified: `aiobot-20260712-065027.sql.gz` → `sha256sum -c` = OK.
- Rollback-теги образов: `chatgptflashbot-{api,bot,worker,beat,migrate}:rollback-20260712-121634`.
- Снапшот каталога: `/home/ubuntu/CHATGPTFLASHBOT.predeploy.20260712-121634` (14M).

**Инцидент, пойман до рестарта (zero-trust):** первый `git archive` внёс CRLF (глобальный
`core.autocrlf`) — `scripts/backup.sh` получил `#!/bin/sh\r`. Пересобрано с `core.autocrlf=false`,
проверено по blob-хэшу до передачи. На сервере после фикса: `Caddyfile`=`def9093b…`,
`backup.sh`=`8abdb2de…` (LF, == repo blobs).

**Cutover:** `docker compose -f docker-compose.yml -f docker-compose.prod.yml` → `build` →
`run --rm migrate` (no-op, DB на `0042`) → `up -d` (api/bot/worker/beat пересозданы) →
`up -d --force-recreate caddy`. Даунтайм ~30–60с.

**Post-deploy verify (всё зелёное):**
- api `healthy`; local `/health=200`, `/health/ready=200`, `/health/providers=401` (auth-protected).
- Публично: `https://superaibot.duckdns.org/health=200`, `/metrics=403` (новый edge-блок), `/miniapp/=200`.
- `alembic current` = `0042_search_model (head)`.
- Живые образы: api `c69e4b05`, bot `65bf8ad6`, worker `7ca14d51`, beat `c58941b9` (пересобраны).
- RestartCount api/bot/worker/beat/caddy = 0; error-scan (2 мин) пусто.

**SHA-эквивалентность:** local `2ea538d` == GitHub `2ea538d` == AWS (`.DEPLOYED_SHA=2ea538d`
+ байтовое равенство критичных файлов repo-блобам).

**Rollback (если понадобится):** `cp -a` из `CHATGPTFLASHBOT.predeploy.20260712-121634` обратно,
`docker tag chatgptflashbot-<svc>:rollback-20260712-121634 …:latest`, `up -d --force-recreate`.
БД-бэкап `aiobot-20260712-065027.sql.gz` (checksum OK) как последний рубеж.

## Оставшиеся действия владельца (requires production verification)
1. **[P0-если-открыт]** AWS Security Group: подтвердить, что `5432/6379/9000/9001/20128/8000` закрыты
   извне (публично только `22` c owner-IP и `80/443`). Хостового firewall нет, `ports: []` в оверлее
   базовые порты не закрывает — защита только на SG.
2. Убрать rollback-снапшот/теги после подтверждения стабильности (диск 62%).
3. Восстановить GitHub Actions (billing) — вернуть CI-гейт для будущих деплоев.
