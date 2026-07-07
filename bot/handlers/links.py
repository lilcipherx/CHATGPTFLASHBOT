"""/links — show admin-defined custom inline LINK buttons (ТЗ §8 «конструктор кнопок»).

The buttons live in the live business_config (``custom_buttons`` = [{text, url}]),
editable from the admin panel without a redeploy. We render one URL button per row,
skipping any whose URL isn't a safe link scheme. Banned users are stopped by
BanMiddleware, but we re-check defensively so the handler is safe in isolation.
"""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from core.i18n import Translator
from core.models import User
from core.services import pricing

router = Router()

_ALLOWED_SCHEMES = ("http://", "https://", "tg://")


def build_links_keyboard(
    buttons: list[dict],
    redirect_base: str = "",
) -> InlineKeyboardMarkup | None:
    """Build a link keyboard from button entries.

    Each entry needs {text, url} and a URL starting with an allowed scheme
    (http/https/tg); others are skipped. Optional fields shape the layout, all
    backward-compatible (an entry without them behaves exactly as before):
      * ``enabled`` False  -> hidden;
      * ``icon`` (emoji)   -> prefixed to the button label;
      * ``row`` (int)      -> consecutive buttons sharing a row index are placed on
                              one keyboard row (multi-column); a button without a row
                              index gets its own row.

    When ``redirect_base`` is set (a public https base, e.g. the webhook URL) and a
    button has a stable ``id``, the button points at ``{base}/r/{id}`` so taps are
    counted by the click tracker (which 302s to the real URL). Without a base — local
    polling dev — the raw URL is used unchanged, so nothing breaks off a public deploy.
    Returns None when no valid buttons remain (caller shows a "not configured" hint)."""
    rows: list[list[InlineKeyboardButton]] = []
    cur_row: int | None = None  # row index of the keyboard row currently being filled
    base = redirect_base.rstrip("/")
    for b in buttons or []:
        if b.get("enabled") is False:
            continue
        text = str(b.get("text") or "").strip()
        url = str(b.get("url") or "").strip()
        if not text or not url.startswith(_ALLOWED_SCHEMES):
            continue
        icon = str(b.get("icon") or "").strip()
        label = f"{icon} {text}" if icon else text
        bid = str(b.get("id") or "").strip()
        # Route through the click tracker only when we have BOTH a public base and a
        # stable id, and the destination is http(s) (tg:// deep links can't be 302'd
        # through a web redirect, so those keep their raw URL).
        href = (
            f"{base}/r/{bid}"
            if base and bid and url.startswith(("http://", "https://"))
            else url
        )
        btn = InlineKeyboardButton(text=label, url=href)
        row_key = b.get("row")
        row_key = row_key if isinstance(row_key, int) and not isinstance(row_key, bool) else None
        if row_key is not None and rows and row_key == cur_row:
            rows[-1].append(btn)          # extend the current multi-column row
        else:
            rows.append([btn])            # start a new keyboard row
            cur_row = row_key
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


@router.message(Command("links"))
async def cmd_links(
    message: Message, session: AsyncSession, user: User, _: Translator
) -> None:
    if user.is_banned:
        return
    from core.config import settings

    buttons = await pricing.custom_buttons(session)
    keyboard = build_links_keyboard(buttons, redirect_base=settings.webhook_base_url)
    if keyboard is None:
        await message.answer(_("links.none"))
        return
    await message.answer(_("links.title"), reply_markup=keyboard)
