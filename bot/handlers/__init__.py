"""Aggregate all handler routers in include order."""
from aiogram import Router

from bot.handlers import (
    account,
    bonus,
    chat,
    contests,
    context,
    documents,
    gift,
    groups,
    inline,
    invite,
    kling,
    links,
    menus,
    misc,
    model,
    music_gen,
    packs_buy,
    photo,
    premium,
    promo,
    roles,
    search,
    settings,
    start,
    support,
    video,
)


def setup_routers() -> Router:
    root = Router()
    # command/menu routers first, free-text chat last (catch-all)
    root.include_router(start.router)
    root.include_router(misc.router)
    root.include_router(account.router)
    root.include_router(bonus.router)
    root.include_router(search.router)
    root.include_router(model.router)
    root.include_router(settings.router)
    root.include_router(roles.router)
    root.include_router(support.router)
    root.include_router(invite.router)
    root.include_router(contests.router)
    root.include_router(links.router)
    root.include_router(inline.router)  # inline_query — distinct update type
    root.include_router(menus.router)
    root.include_router(photo.router)
    root.include_router(kling.router)  # before video: handles video:kling_* exactly
    root.include_router(video.router)
    root.include_router(music_gen.router)
    root.include_router(packs_buy.router)
    root.include_router(gift.router)  # before premium: owns gift: payment payloads
    root.include_router(premium.router)
    root.include_router(promo.router)
    root.include_router(context.router)
    root.include_router(documents.router)
    root.include_router(groups.router)  # before chat: claims group @mentions/replies
    root.include_router(chat.router)  # must be last
    return root
