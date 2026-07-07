# Security

## Reporting
Email the maintainer (see `SUPPORT_CONTACT`, default `@lilcipher`) privately. Do
not open public issues for vulnerabilities.

## Controls in place
**AuthN/Z**
- Admin: email + argon2 password + TOTP 2FA → JWT (httpOnly, SameSite=strict,
  Secure cookie; in-memory access token fallback for cross-origin dev). Server-side
  revocation via `token_version`. RBAC: support < moderator < admin < superadmin.
- Admin API additionally gated by IP allow-list (Caddy + app-level).
- Mini App: Telegram `initData` HMAC-verified, with `auth_date` replay window.
- Bot: throttle middleware (Redis fixed-window) + ban middleware (single source).

**Payments**
- Idempotent on `gateway_tx_id` (unique); webhook amount validated against the
  quote embedded at checkout. YooKassa re-fetched server-side (no body trust) +
  source-IP allow-list; Stripe/Tribute signature-verified. Transient verify
  failures return 5xx (gateway retries) vs forgeries 200.

**Input / content**
- Uploads validated by magic bytes + Pillow decode (not extension); size caps.
- All free-text generation prompts (bot **and** Mini App) pass moderation
  (local rules fail-closed + OpenAI Moderation).
- SQL via ORM params only; AI output sent with `parse_mode=None` (no HTML inject).

**SSRF / secrets**
- Admin-set AI `base_url` validated: http(s) only, private/loopback IPs rejected,
  optional host allowlist (`AI_BASE_URL_ALLOWLIST`).
- Stored AI keys encrypted at rest (Fernet, `ENC_SECRET`).
- Secrets never committed (`.env`, `*.db`, `ADMIN_LOGIN.txt` gitignored).
- Startup fails closed on default `ADMIN_JWT_SECRET` / wildcard CORS on public deploy.

**Transport / infra**
- Caddy auto-TLS; `/api/admin` blocked on the public host (served only on the
  IP-allow-listed `admin.$DOMAIN`); `/metrics` 403 on the public host.

## Hardening checklist (pre-prod)
- [ ] Strong unique `ADMIN_JWT_SECRET`, `ENC_SECRET`, DB/MinIO passwords.
- [ ] `CORS_ORIGINS` = exact Mini App origin; `ADMIN_IP_ALLOWLIST` set.
- [ ] `METRICS_TOKEN` set (or `/metrics` unreachable).
- [ ] Payment webhook signature secrets configured; `TRIBUTE_API_VERIFIED` only
      after confirming the field mapping.
- [ ] `DEV_WEBAPP_BYPASS=false`.
- [ ] `pip-audit` / `bandit` clean in CI; Dependabot enabled.
- [ ] Backups running + a restore drill passed (`scripts/restore_test.sh`).

## Automated scanning
CI runs `pip-audit` (deps) and `bandit` (static) on every push; Dependabot opens
weekly update PRs for pip/npm/actions/docker.
