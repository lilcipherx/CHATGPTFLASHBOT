"""Channel autoposting worker (ТЗ §7) — publish due channel posts to Telegram.

Mirrors dispatch_scheduled_broadcasts: a beat cron scans for due rows and sends
each one. Unlike broadcasts (a user fan-out), a channel post is a single send to
a channel chat, so it is published inline here rather than enqueued."""
from __future__ import annotations

from datetime import UTC, datetime

from arq import cron

from core.db import SessionFactory
from core.models.channel_post import ChannelPost  # FIX: AUDIT13-H1 - module-scope import so sweep_stuck_channel_posts (a separate function) can reference it; previously only imported locally inside dispatch_channel_posts, so the sweep cron raised NameError on every tick and never recovered SIGKILL-stuck posts.
from core.services import channel_posts


def _markup(button_text: str | None, button_url: str | None):
    """Optional inline link button under the post (both text+url required)."""
    if button_text and button_url:
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        return InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=button_text, url=button_url)]]
        )
    return None


async def dispatch_channel_posts(ctx) -> None:
    """Beat cron: publish every due channel post, one row at a time.

    Each post is sent under its own try/except so one bad channel can't block the
    rest, and is flipped to sent/failed so a later tick won't re-publish it."""
    from core.bot_client import get_bot

    now = datetime.now(UTC)
    async with SessionFactory() as session:
        posts = await channel_posts.due(session, now)
        if not posts:
            return
        bot = get_bot()
        from sqlalchemy import update as _update
        from core.models.channel_post import ChannelPost
        for post in posts:
            # FIX: R8 - atomic claim (pending→sending) BEFORE the slow Telegram send so
            # two beat ticks running close together can't both pick the same due post
            # and double-publish it. If the claim loses (rowcount==0), another tick
            # already owns it — skip. Re-read the row after the claim so we send the
            # post's CURRENT content (an admin may have edited it between due() and now).
            claim = await session.execute(
                _update(ChannelPost)
                .where(ChannelPost.id == post.id, ChannelPost.status == "pending")
                .values(status="sending")
            )
            if claim.rowcount == 0:
                continue  # another tick already claimed it
            await session.commit()
            fresh = await session.get(ChannelPost, post.id)
            if fresh is None:
                continue
            markup = _markup(fresh.button_text, fresh.button_url)
            # FIX: F6 - wrap per-post cycle in try/finally so a crash after the claim
            # doesn't leave the post permanently stuck in 'sending' (no sweep exists
            # for 'sending' posts). In finally, if status is still 'sending', flip to 'failed'.
            try:
                if fresh.photo_url:
                    await bot.send_photo(
                        chat_id=fresh.channel,
                        photo=fresh.photo_url,
                        caption=fresh.text or None,
                        parse_mode="HTML",
                        reply_markup=markup,
                    )
                else:
                    await bot.send_message(
                        chat_id=fresh.channel,
                        text=fresh.text,
                        parse_mode="HTML",
                        reply_markup=markup,
                        disable_web_page_preview=True,
                    )
                await channel_posts.mark_sent(session, fresh)
            except Exception as exc:  # noqa: BLE001 — bad channel / Telegram error
                await channel_posts.mark_failed(session, fresh, str(exc))
            finally:
                # FIX: F6 - if the post is still 'sending' after try/except (e.g. mark_sent
                # or mark_failed raised), flip it to 'failed' so it's not stuck forever.
                from sqlalchemy import update as _update2
                stale_check = await session.execute(
                    _update2(ChannelPost)
                    .where(ChannelPost.id == post.id, ChannelPost.status == "sending")
                    .values(status="failed", error="stuck in sending (worker crash)")
                )
                if stale_check.rowcount > 0:
                    await session.commit()


# Publish due posts every minute (like dispatch_scheduled_broadcasts).
publish_channel_posts = cron(dispatch_channel_posts, minute=set(range(0, 60, 1)))


# FIX: AUDIT12-41 - sweep stuck 'sending' channel posts every 5 minutes.
# Same recovery pattern as sweep_stuck_broadcasts: a SIGKILL leaves a post
# 'sending' forever; this sweep marks posts older than 1h as 'failed'.
# Registered in workers/main.py BeatSettings.cron_jobs.
async def sweep_stuck_channel_posts(ctx) -> None:
    """Beat cron: mark 'sending' channel posts stuck for >1h as 'failed'."""
    from datetime import UTC, datetime, timedelta
    from sqlalchemy import update

    cutoff = datetime.now(UTC) - timedelta(hours=1)
    async with SessionFactory() as session:
        res = await session.execute(
            update(ChannelPost)
            .where(ChannelPost.status == "sending", ChannelPost.updated_at < cutoff)
            .values(status="failed", error="stuck in sending (sweep recovery)")
            .execution_options(synchronize_session=False)
        )
        if res.rowcount:
            import structlog
            structlog.get_logger().warning(
                "channel_posts.stuck_sweep", recovered=res.rowcount,
            )
        await session.commit()
