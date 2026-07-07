"""Streaming chat replies (ТЗ §3): with the flag ON the bot assembles streamed
deltas into the final message; with it OFF the buffered chat() path is used."""
from __future__ import annotations

import pytest_asyncio

import bot.handlers.chat as chat
from core.ai_router.base import TextResult
from core.db import SessionFactory, engine
from core.i18n import Translator
from core.models import Base
from core.services.users import get_or_create_user


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


_MID = [1000]


class _Ph:
    def __init__(self, text="", parent=None):
        self.text = text
        self.markup = None
        self._parent = parent  # so chunk-2+ (placeholder.answer) land in msg.sent
        self.chat = type("C", (), {"id": 1})()
        _MID[0] += 1
        self.message_id = _MID[0]

    async def edit_text(self, body, **k):
        self.text = body
        self.markup = k.get("reply_markup", self.markup)

    async def answer(self, body="", **k):
        ph = _Ph(body, parent=self._parent)
        ph.markup = k.get("reply_markup")
        if self._parent is not None:
            self._parent.sent.append(ph)
        return ph


class _Bot:
    async def send_chat_action(self, *a, **k):
        return None


class _Msg:
    def __init__(self):
        self.sent: list[_Ph] = []
        self.bot = _Bot()
        self.chat = type("C", (), {"id": 1})()

    async def answer(self, body="", **k):
        ph = _Ph(body, parent=self)
        ph.markup = k.get("reply_markup")
        self.sent.append(ph)
        return ph


def _cfg(streaming: bool):
    async def _inner(session):
        return {"streaming_enabled": streaming, "markdown_enabled": False, "memory_pairs": 5}
    return _inner


async def test_streaming_assembles_full_text(monkeypatch):
    async def fake_stream(model_key, prompt, *, system=None, history=None, locale="ru"):
        for part in ["Hello", ", ", "world", "!"]:
            yield part
    monkeypatch.setattr(chat, "ai_chat_stream", fake_stream)
    monkeypatch.setattr(chat.pricing, "chat_config", _cfg(True))

    async with SessionFactory() as s:
        user, _c = await get_or_create_user(s, 9001)
        msg = _Msg()
        await chat._answer_text(msg, s, user, Translator("ru"), "hi")
        # The placeholder was edited to the fully-assembled streamed text.
        assert any("Hello, world!" in p.text for p in msg.sent)


async def test_flag_off_uses_buffered(monkeypatch):
    called = {"stream": 0, "buffered": 0}

    async def fake_stream(*a, **k):
        called["stream"] += 1
        if False:  # pragma: no cover — make it an async generator
            yield ""

    async def fake_chat(model_key, prompt, **k):
        called["buffered"] += 1
        return TextResult(text="buffered answer", model=model_key)

    monkeypatch.setattr(chat, "ai_chat_stream", fake_stream)
    monkeypatch.setattr(chat, "ai_chat", fake_chat)
    monkeypatch.setattr(chat.pricing, "chat_config", _cfg(False))

    async with SessionFactory() as s:
        user, _c = await get_or_create_user(s, 9002)
        msg = _Msg()
        await chat._answer_text(msg, s, user, Translator("ru"), "hi")
        assert called["buffered"] == 1 and called["stream"] == 0
        assert any("buffered answer" in p.text for p in msg.sent)


# ---- long-reply chunking (Telegram's 4096-char cap) ------------------------
def test_split_text_keeps_short_text_single():
    assert chat._split_text("hello") == ["hello"]
    assert chat._split_text("") == [""]


def test_split_text_chunks_under_limit_without_splitting_words():
    text = " ".join(f"word{i}" for i in range(4000))  # ~30k chars
    parts = chat._split_text(text)
    assert len(parts) > 1
    assert all(len(p) <= chat._CHUNK_LIMIT for p in parts)
    # rejoining on spaces reproduces the original tokens (no word was cut)
    assert " ".join(parts).split() == text.split()


def test_split_text_prefers_paragraph_boundaries():
    block = "A" * 2000
    text = f"{block}\n\n{block}\n\n{block}"  # 3 paragraphs, each under the limit
    parts = chat._split_text(text)
    assert len(parts) >= 2
    # no chunk should start or end mid-paragraph-block beyond the boundary
    assert all(len(p) <= chat._CHUNK_LIMIT for p in parts)


async def test_long_reply_sent_in_multiple_messages():
    """A >4096-char reply must be delivered as several messages, with the action
    buttons on the LAST one only (not lost)."""
    long_md = "x" * 9000
    msg = _Msg()
    sentinel = object()
    await chat._send_reply(msg, long_md, markdown=False, reply_markup=sentinel)
    assert len(msg.sent) >= 3  # 9000 / 3900 -> 3 chunks
    assert all(len(p.text) <= chat.TG_MAX for p in msg.sent)
    # buttons only on the final chunk
    assert msg.sent[-1].markup is sentinel
    assert all(p.markup is None for p in msg.sent[:-1])


async def test_chunked_reply_stashes_full_text():
    """The full answer is stashed under the LAST message id so translate/voice can
    act on the whole reply, not just the final chunk."""
    from core.services import context as ctx

    long_md = "z" * 9000
    msg = _Msg()
    await chat._send_reply(msg, long_md, markdown=False, reply_markup=object())
    last = msg.sent[-1]
    stored = await ctx.get_full_reply(last.chat.id, last.message_id)
    assert stored == long_md
    # a short (single-message) reply is NOT stashed (nothing to reassemble)
    msg2 = _Msg()
    await chat._send_reply(msg2, "short", markdown=False, reply_markup=object())
    one = msg2.sent[-1]
    assert await ctx.get_full_reply(one.chat.id, one.message_id) is None


async def test_long_streamed_reply_chunked(monkeypatch):
    """A long streamed answer: first chunk edits the placeholder, the rest are new
    messages, and the full text is delivered across them."""
    async def fake_stream(model_key, prompt, *, system=None, history=None, locale="ru"):
        yield "y" * 9000
    monkeypatch.setattr(chat, "ai_chat_stream", fake_stream)
    monkeypatch.setattr(chat.pricing, "chat_config", _cfg(True))

    async with SessionFactory() as s:
        user, _c = await get_or_create_user(s, 9003)
        msg = _Msg()
        await chat._answer_text(msg, s, user, Translator("ru"), "hi")
        joined = "".join(p.text for p in msg.sent)
        assert joined.count("y") == 9000
        assert all(len(p.text) <= chat.TG_MAX for p in msg.sent)
