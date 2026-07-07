"""Ad injection for free users (ТЗ §6 «реклама бесплатным; Premium без рекламы»).

A light monetization nudge: free users get an admin-configured ad appended after
every Nth reply. Premium users never see ads. All knobs live in business_config
(disabled by default), so the whole feature is inert until an admin turns it on.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from core.models import User
from core.services import pricing


async def ad_for_reply(session: AsyncSession, user: User, reply_index: int) -> str | None:
    """Ad text to append for this free-user reply, or None.

    ``reply_index`` is a monotonically increasing per-user counter (e.g. the user's
    weekly text count). Premium users and a disabled/empty config yield None. The ad
    fires when ``reply_index`` is a positive multiple of ``every_n``."""
    if user.is_premium:
        return None
    cfg = await pricing.ads(session)
    if not cfg["enabled"]:
        return None
    n = cfg["every_n"]
    if reply_index <= 0 or n <= 0 or reply_index % n != 0:
        return None
    return cfg["text"] or None
