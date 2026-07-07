"""Import-level wiring test: the full bot dispatcher and FastAPI app must build
without a live bot token / DB connection.

Note: aiogram handler routers are module-level singletons, so the dispatcher is
built exactly once per process (as in production). We therefore assert against a
single build_dispatcher() call."""
from __future__ import annotations


def test_dispatcher_and_routers_build():
    from bot.main import COMMANDS, build_dispatcher

    dp = build_dispatcher()
    assert dp is not None
    # handler routers attached (start, misc, account, search, model, settings,
    # menus, premium, context, chat)
    root = dp.sub_routers[0]
    # start, misc, account, bonus, search, model, settings, roles, support, invite,
    # contests, links, inline, menus, photo, kling, video, music_gen, packs_buy,
    # gift, premium, promo, context, documents, groups, chat
    assert len(root.sub_routers) == 26
    assert len(COMMANDS) == 12  # /start /account /premium /deletecontext /photo
    #                             /video /music /s /model /settings /help /privacy


def test_api_app_builds():
    from api.main import app

    paths = {r.path for r in app.routes}
    assert "/health" in paths
    assert "/api/profile" in paths
    assert "/webhook/telegram" in paths
