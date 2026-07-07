"""Click-tracking redirect for admin /links buttons (ТЗ §8).

A Telegram URL button can't report taps, so the bot can render each button as
``{public_base}/r/{id}`` instead of the raw URL. Tapping it lands here: we record one
click against the button's stable id and 302 to the URL read LIVE from the current
business_config (so editing the URL in the panel takes effect immediately, and no URL
is ever duplicated in the stats table). Unknown / malformed ids 404."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import update  # FIX: B5 - needed for atomic click-count UPDATE
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from core.models import CustomButtonStat
from core.redis_client import first_seen
from core.services import pricing

router = APIRouter(tags=["redirect"])

_ALLOWED_SCHEMES = ("http://", "https://", "tg://")
# Count one click per IP per button per hour so a tap (often re-fetched by link
# previewers / double-taps) and crude hammering don't inflate the click stat.
_CLICK_DEDUP_TTL = 3600


@router.get("/r/{button_id}")
async def track_and_redirect(
    button_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    buttons = await pricing.custom_buttons(session)
    target = next((b for b in buttons if str(b.get("id") or "") == button_id), None)
    url = str((target or {}).get("url") or "")
    if not target or not url.startswith(_ALLOWED_SCHEMES):
        raise HTTPException(status_code=404, detail="link not found")

    # Always redirect; only the COUNT is deduped (a repeat tap still works). When the
    # client IP is unknown, count rather than collapse every such caller into one shared
    # bucket — never under-count. client.host is the real client IP under the same
    # proxy-header trust the YooKassa IP allowlist already relies on.
    ip = request.client.host if request.client else ""
    if not ip or await first_seen(f"btn:clk:{ip}:{button_id}", _CLICK_DEDUP_TTL):
        # FIX: M6 - atomic conditional UPDATE so two concurrent first-taps for the same
        # button_id don't both INSERT and trip a unique-PK violation (the previous
        # get-or-create pattern had a TOCTOU race). On rowcount==0 the stat row already
        # exists → fall back to a plain UPDATE of clicks. Both branches are wrapped so a
        # transient IntegrityError on the insert is recovered by the update path.
        from sqlalchemy.exc import IntegrityError
        now = datetime.now(UTC)
        try:
            res = await session.execute(
                update(CustomButtonStat)
                .where(CustomButtonStat.button_id == button_id)
                .values(clicks=CustomButtonStat.clicks + 1, last_click_at=now)
            )
            if res.rowcount == 0:
                # Row didn't exist yet — INSERT it. A concurrent inserter may win the
                # race; on that IntegrityError we just retry the UPDATE once.
                session.add(CustomButtonStat(button_id=button_id, clicks=1, last_click_at=now))
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    await session.execute(
                        update(CustomButtonStat)
                        .where(CustomButtonStat.button_id == button_id)
                        .values(clicks=CustomButtonStat.clicks + 1, last_click_at=now)
                    )
                    await session.commit()
            else:
                await session.commit()
        except IntegrityError:
            await session.rollback()

    # 302 (temporary): the destination is admin-editable, so it must not be cached.
    return RedirectResponse(url=url, status_code=302)
