"""The global dispatcher error handler (bot.main.on_bot_error) must turn any
unhandled handler exception into a logged, user-visible recovery instead of a
spinning callback button / silent failure."""
from __future__ import annotations

from types import SimpleNamespace

from bot.main import on_bot_error


def _err_event(*, with_callback: bool):
    answered: list[tuple[str, bool]] = []

    async def _answer(text=None, show_alert=False):
        answered.append((text, show_alert))

    cq = (
        SimpleNamespace(data="pay:bad", answer=_answer)
        if with_callback
        else None
    )
    update = SimpleNamespace(update_id=7, callback_query=cq, message=None)
    event = SimpleNamespace(update=update, exception=ValueError("boom"))
    return event, answered


async def test_callback_error_is_answered_and_marked_handled():
    event, answered = _err_event(with_callback=True)
    handled = await on_bot_error(event)
    assert handled is True
    assert len(answered) == 1
    assert answered[0][1] is True  # show_alert


async def test_non_callback_error_is_handled_without_answer():
    event, _ = _err_event(with_callback=False)
    handled = await on_bot_error(event)
    assert handled is True  # still swallowed (logged), nothing to answer


async def test_answer_failure_is_swallowed():
    # An expired/already-answered callback raises on answer — must not re-raise.
    async def _boom(text=None, show_alert=False):
        raise RuntimeError("query is too old")

    cq = SimpleNamespace(data="x", answer=_boom)
    update = SimpleNamespace(update_id=1, callback_query=cq, message=None)
    event = SimpleNamespace(update=update, exception=ValueError("boom"))
    assert await on_bot_error(event) is True
