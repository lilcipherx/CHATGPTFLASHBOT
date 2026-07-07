# Деплой на AWS (EC2 + Docker Compose) — пошагово

Этот файл — про **инфраструктуру AWS**. Про `.env`, секреты, миграции, вебхуки и
создание админа читай `DEPLOYMENT.md` (шаги 1–7) — здесь на них есть ссылки.

Стек поднимается одной командой `docker compose` (prod-оверлей уже в репозитории:
`docker-compose.yml` + `docker-compose.prod.yml`), поэтому на сервере нужен только Docker.

---

## 0. Выбор инстанса (важно — из-за лимитов памяти)

Прод-компоуз запускает много контейнеров. Ориентир по RAM:

| Вариант | Инстанс | RAM | Что запускать |
|---|---|---|---|
| **Полный стек** | `t3.large` | 8 GB | всё: postgres, redis, pgbouncer, omniroute, minio, bot, api, worker, beat, caddy, backup |
| **Экономный** | `t3.medium` | 4 GB | без `omniroute`/`minio` (если чат идёшь через прямые ключи OpenAI/OpenRouter и без S3 на 1 реплике) |

- ОС: **Ubuntu 22.04 LTS** (x86_64), диск **30+ GB gp3**.
- Регион — ближе к аудитории (для РФ обычно `eu-central-1` / `eu-north-1`).

---

## 1. Security Group (файрвол)

Открыть **только**:
- `22/tcp` — SSH, **источник = твой IP** (не 0.0.0.0/0).
- `80/tcp` и `443/tcp` — источник `0.0.0.0/0` (Caddy + TLS).

**НЕ открывать** `5432/6379/9000/4000/20128` — прод-оверлей и так их не публикует
(`ports: []`), доступ к БД/Redis/MinIO/шлюзам только внутри Docker-сети.

---

## 2. Elastic IP + DNS (duckdns)

1. Выдели **Elastic IP** и привяжи к инстансу (чтобы IP не менялся при перезапуске).
2. Наведи домен `superaibot.duckdns.org` на этот IP:
   зайди на duckdns.org → у своего домена впиши Elastic IP в поле **current ip** → Update.
3. Проверь: `ping superaibot.duckdns.org` возвращает твой Elastic IP.

> Caddy сам получит и продлит TLS-сертификат Let's Encrypt для этого домена —
> ничего вручную настраивать не нужно (нужны лишь открытые 80/443 и рабочий DNS).

---

## 3. Установка Docker на сервере

```bash
ssh ubuntu@<ELASTIC_IP>

sudo apt-get update && sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo tee /etc/apt/keyrings/docker.asc >/dev/null
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update && sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker ubuntu && newgrp docker   # запускать docker без sudo
docker compose version                            # проверка
```

---

## 4. Забрать приватный репозиторий на сервер

Репозиторий приватный (`github.com/lilcipherx/CHATGPTFLASHBOT`) — нужен доступ. Проще всего
**fine-grained Personal Access Token** (только чтение этого репо):

1. GitHub → Settings → Developer settings → Personal access tokens → Fine-grained →
   Generate: Repository access = только `CHATGPTFLASHBOT`, Permissions → Contents = **Read-only**.
2. На сервере:
   ```bash
   git clone https://<PAT>@github.com/lilcipherx/CHATGPTFLASHBOT.git
   cd CHATGPTFLASHBOT
   ```
   (`<PAT>` — вставь токен; он не сохраняется в истории, если сразу очистишь: `history -c`.)

> Альтернатива — deploy key (SSH): сгенерируй ключ на сервере `ssh-keygen -t ed25519`,
> добавь публичный в репо → Settings → Deploy keys (read-only), клонируй по `git@github.com:...`.

---

## 5. Собрать SPA (Mini App + Admin)

Caddy раздаёт `./miniapp/dist` и `./admin/dist`, поэтому эти папки должны существовать.
Ставим Node 20 и собираем **на сервере**:

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
(cd miniapp && npm ci && npm run build)   # для split-origin: VITE_API_BASE=https://api... npm run build
(cd admin   && npm ci && npm run build)
```
Топология same-origin (Caddy отдаёт и SPA, и `/api` на одном домене) — `VITE_API_BASE`
оставляй пустым, дефолтная сборка подходит.

---

## 6. Боевой `.env`

Создай `.env` в корне проекта по инструкции **`DEPLOYMENT.md` §1** (там перечислены все
переменные из `core/config.py`). Обязательный минимум для этого домена:

```dotenv
ENV=prod
BOT_MODE=webhook
DOMAIN=superaibot.duckdns.org
WEBHOOK_BASE_URL=https://superaibot.duckdns.org
CORS_ORIGINS=https://superaibot.duckdns.org
ADMIN_ALLOW_IP=<твой_IP>/32          # кто пускается в /api/admin на уровне Caddy
POSTGRES_PASSWORD=<сильный>
ADMIN_JWT_SECRET=<сильный, не change-me>
ENC_SECRET=<сильный, отдельный от JWT>
BOT_TOKEN=<от @BotFather>
# S3/MinIO, платёжки, AI-ключи, SUNO_MODEL и т.д. — по DEPLOYMENT.md
```

Быстрая проверка, что небезопасных дефолтов не осталось (иначе прод намеренно не стартует):
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm api \
  python -c "from core.config import settings; print('config OK')"
```

---

## 7. Запуск стека

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps        # все healthy?
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f api bot worker
```
Миграции применит одноразовый сервис `migrate` (`alembic upgrade head`) — `bot/api/worker/beat`
стартуют только после его успешного завершения. Каталог AI-моделей засевается автоматически.

---

## 8. После старта

1. **Админ**: `docker compose ... run --rm api python -m scripts.create_admin you@mail.com 'Пароль' superadmin`
   (выведет `otpauth://` — отсканируй в Authenticator).
2. **Telegram webhook** регистрируется сам при старте бота на
   `https://superaibot.duckdns.org/webhook/telegram`. Проверь логи бота.
3. **Вебхуки платёжек** в кабинетах провайдеров → `https://superaibot.duckdns.org/webhook/{yookassa|stripe|crypto|tribute}` (см. `DEPLOYMENT.md` §6).
4. **AI-чат** через OmniRoute — `DEPLOYMENT.md` §6.5.
5. Зайди в админку `https://superaibot.duckdns.org/admin/`, проверь Dashboard/Health.

---

## 9. Обновление кода в будущем

```bash
cd CHATGPTFLASHBOT
git pull
(cd miniapp && npm ci && npm run build) && (cd admin && npm ci && npm run build)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

---

## Частые грабли
- **502/нет TLS** — DNS ещё не указывает на Elastic IP, или закрыты 80/443 в Security Group.
- **api unhealthy** — не заполнен `.env` (конфиг падает на дефолтных секретах — это by design).
- **Не хватает RAM / OOM** — возьми инстанс побольше или убери `omniroute`/`minio`.
- **admin 403** — твой IP не в `ADMIN_ALLOW_IP` (Caddy режет `/api/admin` на уровне прокси).
- **Suno выдаёт старую версию** — задай точный id модели в **админке** (API-ключи → блок «Suno») или через `SUNO_MODEL=<id>` в `.env`. Значение из админки перекрывает `.env`.
