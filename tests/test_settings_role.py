"""The custom role (system prompt prepended to every AI request) is length-capped
at the input boundary so it can't be used to inflate token cost / blow the context
window. Over the limit is rejected (not saved, not truncated) and the user stays in
the role-input state."""
from __future__ import annotations

from types import SimpleNamespace

from bot.handlers import settings


def _ctx():
    saved: list = []
    cleared: list = []
    answered: list = []

    async def _set_role(_session, _user, role):
        saved.append(role)

    async def _answer(text=None, **kw):
        answered.append(text)

    async def _clear():
        cleared.append(True)

    return saved, cleared, answered, _set_role, _answer, _clear


async def test_oversized_role_rejected(monkeypatch):
    saved, cleared, answered, _set_role, _answer, _clear = _ctx()
    monkeypatch.setattr(settings, "set_role", _set_role)

    message = SimpleNamespace(text="x" * (settings.MAX_ROLE_LEN + 1), answer=_answer)
    state = SimpleNamespace(clear=_clear)
    user = SimpleNamespace(user_id=1)

    await settings.role_received(message, state, session=None, user=user,
                                 _=lambda k, **kw: f"{k}:{kw.get('limit', '')}")

    assert saved == []                       # nothing persisted
    assert cleared == []                     # stays in the role-input state
    assert any("settings.role.too_long" in (a or "") for a in answered)


async def test_normal_role_saved(monkeypatch):
    saved, cleared, answered, _set_role, _answer, _clear = _ctx()
    monkeypatch.setattr(settings, "set_role", _set_role)

    message = SimpleNamespace(text="Be a helpful pirate.", answer=_answer)
    state = SimpleNamespace(clear=_clear)
    user = SimpleNamespace(user_id=1)

    await settings.role_received(message, state, session=None, user=user,
                                 _=lambda k, **kw: k)

    assert saved == ["Be a helpful pirate."]
    assert cleared == [True]                  # state cleared on success


async def test_clear_sentinel_clears_role(monkeypatch):
    saved, cleared, answered, _set_role, _answer, _clear = _ctx()
    monkeypatch.setattr(settings, "set_role", _set_role)

    message = SimpleNamespace(text="/clear", answer=_answer)
    state = SimpleNamespace(clear=_clear)
    user = SimpleNamespace(user_id=1)

    await settings.role_received(message, state, session=None, user=user,
                                 _=lambda k, **kw: k)

    assert saved == [None]                    # role cleared
    assert cleared == [True]
