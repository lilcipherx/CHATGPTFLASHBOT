"""User language is stored verbatim from Telegram — never coerced to a fabricated
default. Rendering still falls back to RU for unsupported locales at render time
(core.i18n.t), so honest storage is safe."""
from __future__ import annotations

import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base
from core.services.users import _normalize_lang, get_or_create_user


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


def test_normalize_lang_keeps_real_value_no_fabrication():
    assert _normalize_lang("de") == "de"          # unsupported but REAL — kept
    assert _normalize_lang("EN") == "en"          # lowercased
    assert _normalize_lang("pt-BR") == "pt"       # base subtag
    assert _normalize_lang("zh-Hans") == "zh"
    assert _normalize_lang(None) == ""            # absent → "", not a guess
    assert _normalize_lang("") == ""


async def test_create_user_stores_real_language():
    async with SessionFactory() as s:
        u, created = await get_or_create_user(s, 1, language_code="de")
        assert created and u.language_code == "de"   # NOT coerced to "ru"

        u2, _ = await get_or_create_user(s, 2, language_code=None)
        assert u2.language_code == ""                 # honest unknown, no default


async def test_first_start_shows_language_picker():
    """A brand-new user's first /start shows the language picker, not the welcome."""
    from types import SimpleNamespace

    from bot.handlers.start import cmd_start

    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 10, language_code="en")
        sent: list = []

        async def _answer(text=None, **kw):
            sent.append((text, kw.get("reply_markup")))

        async def _noop(*a, **k):
            pass

        message = SimpleNamespace(answer=_answer, answer_photo=_noop, answer_video=_noop)
        command = SimpleNamespace(args=None)
        state = SimpleNamespace(set_state=_noop)

        await cmd_start(message, command, state, s, user, True, lambda k, **kw: k)

    # exactly one message — the language prompt with a keyboard — and no welcome
    assert len(sent) == 1
    assert sent[0][0] == "settings.lang.choose"
    assert sent[0][1] is not None                       # the onboarding keyboard


async def test_onboarding_lang_callback_stores_choice():
    """Picking a language on first run persists it (an explicit, accurate choice)."""
    from types import SimpleNamespace

    from bot.handlers.start import cb_onboarding_lang

    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 11, language_code="en")

        async def _noop(*a, **k):
            pass

        bot = SimpleNamespace(set_my_commands=_noop)
        chat = SimpleNamespace(id=11)
        msg = SimpleNamespace(
            chat=chat, delete=_noop, answer=_noop, answer_photo=_noop, answer_video=_noop,
        )
        callback = SimpleNamespace(data="onblang:es", answer=_noop, bot=bot, message=msg)
        state = SimpleNamespace(set_state=_noop)

        await cb_onboarding_lang(callback, state, s, user)
        await s.refresh(user)
        assert user.language_code == "es"
