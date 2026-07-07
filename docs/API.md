# API reference

FastAPI auto-generates an interactive spec at **`/docs`** (Swagger) and the raw
OpenAPI JSON at **`/openapi.json`**. This page summarises the surface and auth.

## Auth
- **Mini App** (`/api/*`): header `X-Init-Data: <Telegram initData>`
  (HMAC-verified, replay-windowed). Unauthenticated → 401.
- **Admin** (`/api/admin/*`): httpOnly `admin_access` cookie (or
  `Authorization: Bearer`), obtained from `/api/admin/auth/login`
  (email + password + TOTP). RBAC-gated; IP-allow-listed.
- **Webhooks**: provider signature / source-IP / Telegram secret-token.

## Public
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | liveness |
| GET | `/health/ready` | readiness (DB+Redis) → 200/503 |
| GET | `/health/providers` | configured AI/payment backends (no secrets) |
| GET | `/metrics` | Prometheus exposition (token-gated if set) |

## Mini App (`/api`, requires `X-Init-Data`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/profile` | user, quota, balances, credits |
| GET | `/photo-effects`, `/video-effects`, `/effects` | catalogs (enabled only) |
| GET | `/effects/{kind}/{id}` | effect detail + models + price |
| POST | `/effects/{kind}/{id}/cost` | price for a model/params |
| POST | `/effects/{kind}/{id}/generate` | **moderated**, charge→persist→enqueue |
| POST | `/effects/generate`, `/video-effects/generate` | legacy single-photo effects |
| GET | `/jobs`, `/jobs/{id}` | history / job status |
| GET | `/banners`, `/categories`, `/photo-ratios` | UI data |
| POST | `/billing/invoice-link` | Telegram Stars invoice link |

## Admin (`/api/admin`, JWT + RBAC + IP allow-list)
- `auth/`: `login`, `refresh`, `logout` (token revocation).
- `dashboard` (cached), `payments` + `payments/{id}/refund` (two-phase, retryable).
- `users` (search/card/ban/premium/credits/reset-quota/clear-context).
- `ai/` accounts + models + health (SSRF-validated base_url).
- `effects`, `banners`, `promos`, `referrals/settings`, `flags`, `providers`,
  `gates`, `broadcasts`, `pricing`, `audit`.

Roles: `support < moderator < admin < superadmin` (see `core/services/admin_auth.py`).

## Webhooks
| Path | Verification |
|------|--------------|
| `POST /webhook/telegram` | `X-Telegram-Bot-Api-Secret-Token` (constant-time) |
| `POST /webhook/yookassa` | source-IP allow-list + server-side re-fetch |
| `POST /webhook/stripe` | Stripe signature |
| `POST /webhook/tribute` | HMAC (inert until `TRIBUTE_API_VERIFIED`) |

Webhook responses: **200** ack (incl. definitive rejection — no retry); **503**
on transient verification failure (gateway retries).

## Error conventions
Standard FastAPI `{"detail": ...}`. Notable: 401 (auth), 402 (insufficient
credits), 403 (banned / IP / role), 413/415 (upload), 400 (moderation/validation),
429 (throttle), 503 (queue/dependency unavailable — charge refunded).
