"""Provider kill-switch (§11A.2) — disabled provider keys stored in `pricing`.

ai_router adapters can consult `is_disabled()` to honour a manual kill-switch
(hook), independent of API-key availability."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Pricing

KEY = "providers_disabled"


async def get_disabled(session: AsyncSession) -> list[str]:
    row = await session.get(Pricing, KEY)
    return (row.value or {}).get("disabled", []) if row else []


async def is_disabled(session: AsyncSession, key: str) -> bool:
    """True when ``key`` (a media-provider/service key) is killed by the admin
    switch. Consulted by the media router so a disabled provider is removed from
    generation, not just hidden in the panel."""
    return key in set(await get_disabled(session))


async def set_disabled(session: AsyncSession, keys: list[str]) -> None:
    row = await session.get(Pricing, KEY)
    if row is None:
        row = Pricing(key=KEY, value={"disabled": keys})
        session.add(row)
    else:
        row.value = {"disabled": keys}
    await session.commit()


async def toggle(session: AsyncSession, key: str) -> bool:
    disabled = set(await get_disabled(session))
    if key in disabled:
        disabled.discard(key)
        now_disabled = False
    else:
        disabled.add(key)
        now_disabled = True
    await set_disabled(session, sorted(disabled))
    return now_disabled
