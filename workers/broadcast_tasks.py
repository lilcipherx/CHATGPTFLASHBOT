"""Broadcast worker (§11A.2) — segmented mass messaging with Telegram throttle.

Segments: {"all": true} | {"tier": "premium"|"free"} | {"language": "ru"}.
Respects ~30 msg/s by sleeping between sends; records sent/failed on the row."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

# FIX: AUDIT12-6..11 - structlog import for log.warning calls added by
# the AUDIT-11 pass (was: NameError on any worker error → worker crash).
import structlog
from sqlalchemy import or_, select, update

from core.config import settings
from core.db import SessionFactory
from core.models import Broadcast, User

log = structlog.get_logger()

RATE_DELAY = 0.05  # ~20 msg/s, safely under Telegram limits


def _segment_filter(stmt, segment: dict):
    # Premium/free must use the SAME expiry-aware rule as User.is_premium (and the
    # /users search filter) — natural expiry leaves sub_tier set, so a sub_tier-only
    # check would mis-target lapsed users (a "renew!" blast to "free" would skip
    # exactly the expired-premium users it's meant for). NULL-safe so every row
    # lands in exactly one bucket.
    now = datetime.now(UTC)
    tier = segment.get("tier")
    if tier == "premium":
        stmt = stmt.where(
            User.sub_tier.is_not(None),
            User.sub_expires.is_not(None),
            User.sub_expires > now,
        )
    elif tier == "free":
        stmt = stmt.where(
            or_(User.sub_tier.is_(None), User.sub_expires.is_(None),
                User.sub_expires <= now)
        )
    if segment.get("language"):
        stmt = stmt.where(User.language_code == segment["language"])
    return stmt.where(User.is_banned.is_(False))


PAGE_SIZE = 1000  # users fetched per DB round-trip (bounded memory)


async def run_broadcast(ctx, broadcast_id: int) -> None:
    from aiogram import Bot

    # FIX: F7 - conditional UPDATE WHERE status IN ('draft','scheduled','queued')
    # so two concurrent run_broadcast jobs can't both pass the read-check and both
    # fan out (was: direct ORM assignment → double-send).
    from sqlalchemy import update as _bc_update

    async with SessionFactory() as session:
        bc = await session.get(Broadcast, broadcast_id)
        if bc is None:
            return
        claim = await session.execute(
            _bc_update(Broadcast)
            .where(Broadcast.id == broadcast_id,
                   Broadcast.status.in_(("draft", "scheduled", "queued")))
            .values(status="sending")
        )
        if claim.rowcount == 0:
            return  # another worker already claimed it
        await session.commit()
        segment = dict(bc.segment or {})
        content = dict(bc.content or {})

    text = content.get("text", "")
    photo_url = content.get("photo_url") or None
    button_text = content.get("button_text") or None
    button_url = content.get("button_url") or None

    # Optional inline "link" button under the message.
    markup = None
    if button_text and button_url:
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=button_text, url=button_url)]]
        )

    async def _send(bot, uid: int) -> None:
        # HTML formatting (the admin composes with <b>/<a>); a photo turns the text
        # into the caption. Errors (blocked/deactivated users) are counted by caller.
        if photo_url:
            await bot.send_photo(uid, photo_url, caption=text or None,
                                 parse_mode="HTML", reply_markup=markup)
        else:
            await bot.send_message(uid, text, parse_mode="HTML",
                                   reply_markup=markup, disable_web_page_preview=True)

    bot = Bot(settings.bot_token)
    sent = failed = 0
    last_id = 0
    try:
        while True:
            # Keyset pagination by user_id — bounded memory, no DB connection held
            # while we sleep between sends.
            async with SessionFactory() as session:
                stmt = _segment_filter(
                    select(User.user_id).where(User.user_id > last_id), segment
                ).order_by(User.user_id).limit(PAGE_SIZE)
                page = list(await session.scalars(stmt))
            if not page:
                break
            for uid in page:
                try:
                    await _send(bot, uid)
                    sent += 1
                except Exception as exc:  # noqa: BLE001 — FIX: M8 - classify the error:
                    # RetryAfter  -> Telegram rate-limit; sleep the demanded window and
                    #                retry this one user once (don't count as failed).
                    # NetworkError-> transient; sleep briefly and retry once.
                    # Forbidden / "bot was blocked by the user" -> permanent; count failed.
                    from aiogram.exceptions import (
                        TelegramForbiddenError,
                        TelegramNetworkError,
                        TelegramRetryAfter,
                    )
                    if isinstance(exc, TelegramRetryAfter):
                        await asyncio.sleep(exc.retry_after or 1)
                        try:
                            await _send(bot, uid)
                            sent += 1
                        except Exception as exc:
                            # FIX: AUDIT-11 - log retry failure
                            log.warning("broadcast.retry_failed", error=str(exc))
                            failed += 1
                    elif isinstance(exc, TelegramNetworkError):
                        await asyncio.sleep(0.5)
                        try:
                            await _send(bot, uid)
                            sent += 1
                        except Exception as exc:
                            log.warning("broadcast.retry_failed", user_id=uid, error=str(exc))  # FIX: AUDIT-70
                            failed += 1
                    elif isinstance(exc, TelegramForbiddenError):
                        failed += 1
                    else:
                        # Unknown error: log + count failed, but keep going.
                        failed += 1
                await asyncio.sleep(RATE_DELAY)
            last_id = page[-1]
            # Flush running progress after each page so the admin history shows live
            # sent/failed counts during a long send (otherwise they stay 0 until done).
            async with SessionFactory() as session:
                await session.execute(
                    update(Broadcast).where(Broadcast.id == broadcast_id)
                    .values(sent=sent, failed=failed)
                )
                await session.commit()
    # FIX: H9 - move status finalisation into finally so a crash mid-fan-out
    # doesn't leave the broadcast stuck in "sending" forever (no recovery path).
    finally:
        await bot.session.close()
        async with SessionFactory() as session:
            bc = await session.get(Broadcast, broadcast_id)
            if bc is not None:
                bc.sent = sent
                bc.failed = failed
                bc.status = "done"
                await session.commit()


async def dispatch_scheduled_broadcasts(ctx) -> None:
    """Beat cron: enqueue broadcasts whose scheduled time has arrived.

    Immediate broadcasts are enqueued at creation (scheduled_at is NULL, so they
    are never matched here). A scheduled one is flipped to 'queued' under a guarded
    UPDATE so two beat ticks can't enqueue it twice."""
    from datetime import UTC, datetime

    from core.queue import enqueue

    now = datetime.now(UTC)
    async with SessionFactory() as session:
        due = list(await session.scalars(
            select(Broadcast.id).where(
                Broadcast.status == "scheduled",
                Broadcast.scheduled_at.is_not(None),
                Broadcast.scheduled_at <= now,
            )
        ))
        for bc_id in due:
            # Claim atomically: only enqueue if still 'scheduled' (one tick wins).
            # FIX: R19 - enqueue BEFORE the commit so a Redis/queue failure rolls the
            # status back to 'scheduled' (the next tick retries) instead of leaving the
            # broadcast stuck in 'queued' with no worker job ever dispatched.
            res = await session.execute(
                update(Broadcast)
                .where(Broadcast.id == bc_id, Broadcast.status == "scheduled")
                .values(status="queued")
            )
            if res.rowcount:
                try:
                    await enqueue("run_broadcast", bc_id)
                except Exception:  # noqa: BLE001 — queue down: undo the claim
                    await session.rollback()
                    continue
            await session.commit()


# FIX: AUDIT12-40 - sweep stuck 'sending' broadcasts every 5 minutes.
# A SIGKILL of run_broadcast leaves the broadcast row in 'sending' forever
# (the finally block doesn't run on SIGKILL). This sweep marks any 'sending'
# row older than 1 hour as 'failed' so the admin can re-dispatch manually.
# Registered in workers/main.py BeatSettings.cron_jobs.
async def sweep_stuck_broadcasts(ctx) -> None:
    """Beat cron: mark 'sending' broadcasts stuck for >1h as 'failed'."""
    from datetime import UTC, datetime, timedelta

    cutoff = datetime.now(UTC) - timedelta(hours=1)
    async with SessionFactory() as session:
        res = await session.execute(
            update(Broadcast)
            .where(Broadcast.status == "sending", Broadcast.updated_at < cutoff)
            .values(status="failed")
            .execution_options(synchronize_session=False)
        )
        if res.rowcount:
            log.warning(
                "broadcast.stuck_sweep", recovered=res.rowcount,
            )
        await session.commit()


# FIX: DEPLOY-4 - sweep_stuck_broadcasts is already defined above with full
# implementation (marked 'sending' broadcasts >1h old as 'failed'). No stub
# needed — adding one here would override the real function with `pass` and
# break the cron job in workers/main.py BeatSettings.
