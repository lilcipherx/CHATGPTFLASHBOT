"""Webhook endpoints: Telegram (webhook mode) + payment gateways.

Payment webhooks verify the provider signature, apply the event idempotently
(transactions.gateway_tx_id), and notify the user via the bot."""
from __future__ import annotations

import hmac
import ipaddress

import structlog
from aiogram.types import Update
from fastapi import APIRouter, Request, Response

from core.config import settings
from core.db import SessionFactory
from core.payments import PaymentError, PaymentRetryable, get_provider
from core.payments.service import apply_event

router = APIRouter(tags=["webhooks"])
log = structlog.get_logger()


def _ip_allowed(client_ip: str, networks: str) -> bool:
    """True if client_ip falls inside any CIDR/host in the comma-separated list."""
    try:
        ip = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    for cidr in (c.strip() for c in networks.split(",") if c.strip()):
        try:
            if ip in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


@router.post(settings.webhook_path)
async def telegram_webhook(request: Request) -> Response:
    # Reject forged updates: only Telegram knows the secret token we registered
    # via set_webhook(secret_token=...). Constant-time compare (consistent with the
    # payment-webhook signature checks) so the secret can't be probed via timing.
    received = request.headers.get("x-telegram-bot-api-secret-token") or ""
    if not hmac.compare_digest(received, settings.effective_webhook_secret):
        return Response(status_code=403)
    bot = getattr(request.app.state, "bot", None)
    dp = getattr(request.app.state, "dp", None)
    if bot is None or dp is None:
        return Response(status_code=503)
    update = Update.model_validate(await request.json(), context={"bot": bot})
    # Idempotency against Telegram's webhook REDELIVERY: Telegram retries a delivery
    # on any non-2xx OR timeout, so a slow turn (an AI call now bounded at ~60s) can
    # be redelivered while still processing — re-running the handler would double the
    # quota charge, the provider cost AND the reply. Claim the update_id once (keyed by
    # bot id for multi-bot safety); a duplicate is ACKed 200 without re-feeding. Fail
    # open on a Redis hiccup so a real update is never dropped.
    if not await _claim_update(bot.id, update.update_id):
        return Response(status_code=200)
    await dp.feed_update(bot, update)
    return Response(status_code=200)


# Telegram update_ids are unique+increasing per bot; a 1h claim window comfortably
# covers Telegram's retry schedule without growing Redis unbounded.
_UPDATE_CLAIM_TTL = 3600


async def _claim_update(bot_id: int, update_id: int | None) -> bool:
    """True if this (bot, update_id) is seen for the FIRST time (claim it); False if
    it is a redelivery already being / already handled. Fail-open (returns True) on
    any Redis error so a transient cache outage never drops a real update."""
    if update_id is None:
        return True
    try:
        from core.redis_client import redis_client

        return bool(
            await redis_client.set(
                f"tg:wh:{bot_id}:{update_id}", "1", nx=True, ex=_UPDATE_CLAIM_TTL
            )
        )
    except Exception:  # noqa: BLE001 — dedup is best-effort; never block a real update
        return True


async def _notify(user_id: int, text: str) -> None:
    from core.bot_client import get_bot

    try:
        await get_bot().send_message(user_id, text)
    except Exception as exc:  # noqa: BLE001 — FIX: F32 - log so a payment-success DM
        # failure is observable (was bare `pass` with no signal). Still best-effort:
        # the payment itself already applied; we just couldn't tell the user.
        log.warning("payment.notify_failed", user_id=user_id, error=str(exc))


async def _handle_gateway(gateway: str, request: Request) -> dict | Response:  # FIX: L12
    provider = get_provider(gateway)
    if provider is None:
        return {"ok": False, "error": "unknown gateway"}
    # YooKassa does not sign its webhooks, so verify the source IP against its
    # published notification ranges (the only spoofing defence it offers).
    # FIX: L11 - fail-closed on public deploy if the IP allowlist is empty (was: skip
    # the check entirely when the env var is unset — defense-in-depth gap).
    if gateway == "yookassa":
        # FIX: X6 - wrap the IP check in an else: branch so dev/test with an empty
        # allowlist genuinely skips the check (was: fell through to _ip_allowed("", "")
        # which always returns False → every webhook rejected in dev/test).
        if not settings.yookassa_webhook_ips.strip():
            if settings.is_public_deploy:
                log.warning("payment.yookassa_ip_allowlist_empty", gateway=gateway)
                return {"ok": False, "error": "ip allowlist not configured"}
            # Non-public dev/test: skip the check (legacy behaviour).
        else:
            # FIX: AUDIT13-M5 - behind the reverse proxy, request.client.host is the
            # proxy's socket IP (e.g. 127.0.0.1), not YooKassa's. The Caddyfile rewrites
            # X-Forwarded-For to the real client via {remote_host}, so prefer its
            # right-most hop; fall back to the socket peer for a direct (dev) connection.
            xff = request.headers.get("x-forwarded-for", "")
            client_ip = (xff.split(",")[-1].strip() if xff else "") or (
                request.client.host if request.client else ""
            )
            if not _ip_allowed(client_ip, settings.yookassa_webhook_ips):
                log.warning("payment.webhook_bad_ip", gateway=gateway, ip=client_ip)
                return {"ok": False, "error": "ip not allowed"}
    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    try:
        # FIX: AUDIT-FINAL-2/3 - verify_webhook() is a SYNC method on every
        # gateway (yookassa / stripe / crypto / tribute). The YooKassa + Stripe
        # implementations issue blocking HTTPS calls to the gateway's API inside
        # verify_webhook (Payment.find_one / PaymentIntent.retrieve). Calling
        # those inline in an async route blocks the event loop for the full HTTP
        # round-trip (hundreds of ms under load → cascading latency on every
        # other in-flight request). Run the whole verify chain in a thread.
        import asyncio

        event = await asyncio.to_thread(provider.verify_webhook, headers, body)
    except PaymentRetryable as exc:
        # Transient verification failure (e.g. the authoritative re-fetch timed
        # out). Return 5xx so the gateway RETRIES — a 200 here would make it treat
        # a real, still-unverified payment as handled and never deliver it again.
        log.warning("payment.webhook_retryable", gateway=gateway, error=str(exc))
        return Response(status_code=503)
    except PaymentError as exc:
        # Definitive rejection (bad signature / forgery) — ACK with 200 so the
        # gateway does not keep retrying a request we will never accept.
        log.warning("payment.webhook_rejected", gateway=gateway, error=str(exc))
        return {"ok": False, "error": "invalid signature"}
    if event is None:
        return {"ok": True, "ignored": True}

    locale = "ru"
    async with SessionFactory() as session:
        uid = await apply_event(session, event)
        if uid:
            # Localize the confirmation in the buyer's language (external webhooks
            # carry no Telegram context, so resolve it from the stored user).
            from core.services.users import get_user

            u = await get_user(session, uid)
            locale = (u.language_code if u and u.language_code else "ru")
    if uid:
        from core.i18n import t

        await _notify(uid, t("pay.success", locale))
        log.info("payment.applied", gateway=gateway, user_id=uid, tx=event.gateway_tx_id)
    return {"ok": True}


@router.post("/webhook/yookassa")
async def yookassa_webhook(request: Request) -> dict:
    return await _handle_gateway("yookassa", request)


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request) -> dict:
    return await _handle_gateway("stripe", request)


@router.post("/webhook/tribute")
async def tribute_webhook(request: Request) -> dict:
    return await _handle_gateway("sbp_tribute", request)


@router.post("/webhook/crypto")
async def crypto_webhook(request: Request) -> dict:
    # Crypto Pay signs every webhook (HMAC-SHA256), verified in the provider, so no
    # IP allow-list is needed — a forged body fails the signature check.
    return await _handle_gateway("crypto", request)
