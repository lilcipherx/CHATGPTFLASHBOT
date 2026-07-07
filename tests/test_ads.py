"""Ad injection for free users (ТЗ §6). Disabled by default; Premium never sees ads."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base, User
from core.services import pricing
from core.services.ads import ad_for_reply


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        await pricing.redis_client.delete(pricing._CACHE_KEY)
    except Exception:  # noqa: BLE001
        pass
    yield


def _free() -> User:
    return User(user_id=1, username="u", language_code="ru")


def _premium() -> User:
    u = User(user_id=2, username="p", language_code="ru", sub_tier="premium")
    u.sub_expires = datetime.now(UTC) + timedelta(days=30)
    return u


async def test_disabled_by_default():
    async with SessionFactory() as s:
        assert await ad_for_reply(s, _free(), 5) is None


async def test_enabled_fires_every_nth():
    async with SessionFactory() as s:
        await pricing.set_config(s, {"ads": {"enabled": True, "every_n": 3, "text": "AD"}})
    async with SessionFactory() as s:
        u = _free()
        assert await ad_for_reply(s, u, 1) is None
        assert await ad_for_reply(s, u, 2) is None
        assert await ad_for_reply(s, u, 3) == "AD"
        assert await ad_for_reply(s, u, 6) == "AD"
        assert await ad_for_reply(s, u, 4) is None


async def test_premium_never_sees_ads():
    async with SessionFactory() as s:
        await pricing.set_config(s, {"ads": {"enabled": True, "every_n": 1, "text": "AD"}})
    async with SessionFactory() as s:
        assert await ad_for_reply(s, _premium(), 3) is None


# ---- dedicated ad counter + CTA via _maybe_ad -------------------------------
class _FakeMsg:
    def __init__(self) -> None:
        self.sent: list[tuple[str, object]] = []

    async def answer(self, text, parse_mode=None, reply_markup=None):  # noqa: ANN001
        self.sent.append((text, reply_markup))


async def test_maybe_ad_uses_dedicated_monotonic_counter():
    from bot.handlers.chat import _maybe_ad
    from core.i18n import Translator
    from core.services.users import get_or_create_user

    async with SessionFactory() as s:
        await pricing.set_config(s, {"ads": {"enabled": True, "every_n": 2, "text": "AD"}})
    tr = Translator("ru")
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 10)
        m1 = _FakeMsg()
        await _maybe_ad(m1, s, user, tr)          # count 1 -> no ad
        assert user.ad_reply_count == 1 and m1.sent == []
        m2 = _FakeMsg()
        await _maybe_ad(m2, s, user, tr)          # count 2 -> ad + CTA
        assert user.ad_reply_count == 2
        assert len(m2.sent) == 1 and m2.sent[0][0] == "AD"
        # the ad carries the «remove ads» CTA into the Premium menu
        kb = m2.sent[0][1]
        assert kb is not None
        assert kb.inline_keyboard[0][0].callback_data == "premium:open"


async def test_maybe_ad_counter_advances_even_when_quota_exhausted():
    """The dedicated counter ticks regardless of pay source, so the cadence doesn't
    freeze once a free user is paying from ✨ credits (text_req_week stops growing)."""
    from bot.handlers.chat import _maybe_ad
    from core.i18n import Translator
    from core.services.users import get_or_create_user

    async with SessionFactory() as s:
        await pricing.set_config(s, {"ads": {"enabled": True, "every_n": 3, "text": "AD"}})
    tr = Translator("ru")
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 11)
        user.text_req_week = 100        # quota counter frozen at the cap
        await s.commit()
        for _i in range(3):
            await _maybe_ad(_FakeMsg(), s, user, tr)
        assert user.ad_reply_count == 3  # advanced independently of text_req_week
