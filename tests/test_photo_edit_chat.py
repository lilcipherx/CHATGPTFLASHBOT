"""In-chat photo editing (ТЗ §3): photo + caption → img2img edit, charged from
the image pack, with a refund when the provider is unavailable."""
from __future__ import annotations

import pytest_asyncio

import bot.handlers.chat as chat
from core.ai_router.base import ImageResult, ProviderUnavailable
from core.db import SessionFactory, engine
from core.models import Base, PackBalance
from core.services.users import get_or_create_user


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


class _Bot:
    async def send_chat_action(self, *a, **k):
        return None

    async def download(self, *a, **k):
        import io
        return io.BytesIO(b"imgbytes")


class _Note:
    def __init__(self):
        self.text = None
        self.deleted = False

    async def edit_text(self, t, *a, **k):
        self.text = t

    async def delete(self):
        self.deleted = True


class _CbMsg:
    def __init__(self):
        self.bot = _Bot()
        self.chat = type("C", (), {"id": 1})()
        self.note = _Note()
        self.photos: list = []

    async def edit_reply_markup(self, *a, **k):
        return None

    async def answer(self, *a, **k):
        return self.note

    async def answer_photo(self, photo, *a, **k):
        self.photos.append(photo)


class _Cb:
    def __init__(self, msg):
        self.message = msg

    async def answer(self, *a, **k):
        return None


class _State:
    def __init__(self, **data):
        self.data = data

    async def get_data(self):
        return self.data


async def _balance(s, uid):
    b = await s.get(PackBalance, uid)
    return b.image_credits if b else 0


async def test_edit_charges_and_sends(monkeypatch):
    async def fake_save(data, ext, **k):
        return "/media/uploads/x.png"
    async def fake_gen(service, prompt, cfg):
        assert cfg["image_refs"] == ["/media/uploads/x.png"]
        return [ImageResult(url="http://result/edited.png")]
    monkeypatch.setattr(chat.storage, "save_upload", fake_save)
    monkeypatch.setattr(chat, "generate_image", fake_gen)

    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 7700)
        bal = await s.get(PackBalance, user.user_id)
        bal.image_credits = 5
        await s.commit()

        msg = _CbMsg()
        await chat.cb_photo_edit(
            _Cb(msg), _State(pe_file="f1", pe_prompt="make it blue"),
            s, user, lambda k, **kw: k,
        )
        assert msg.photos == ["http://result/edited.png"]
        assert await _balance(s, user.user_id) == 4  # charged 1


async def test_edit_refunds_when_unavailable(monkeypatch):
    async def fake_save(data, ext, **k):
        return "/media/uploads/x.png"
    async def boom(service, prompt, cfg):
        raise ProviderUnavailable("nano_banana")
    monkeypatch.setattr(chat.storage, "save_upload", fake_save)
    monkeypatch.setattr(chat, "generate_image", boom)

    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 7701)
        bal = await s.get(PackBalance, user.user_id)
        bal.image_credits = 5
        await s.commit()

        msg = _CbMsg()
        await chat.cb_photo_edit(
            _Cb(msg), _State(pe_file="f1", pe_prompt="make it blue"),
            s, user, lambda k, **kw: k,
        )
        assert msg.photos == []  # nothing sent
        assert msg.note.text == "photo.edit_unavailable"
        assert await _balance(s, user.user_id) == 5  # refunded


async def test_edit_no_caption_no_charge(monkeypatch):
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 7702)
        bal = await s.get(PackBalance, user.user_id)
        bal.image_credits = 5
        await s.commit()

        msg = _CbMsg()
        await chat.cb_photo_edit(
            _Cb(msg), _State(pe_file="f1", pe_prompt="   "),
            s, user, lambda k, **kw: k,
        )
        assert await _balance(s, user.user_id) == 5  # not charged
