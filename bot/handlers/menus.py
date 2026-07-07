"""/photo, /video, /music menus (§15.4–15.6) + reply-keyboard shortcuts.

These open the per-modality service menu; picking a service hands off to its real
config-FSM + generation handler (photo -> handlers/photo.py, video -> handlers/
kling.py + video.py, music -> handlers/music_gen.py). A modality whose admin section
is OFF shows its editable "coming soon" text instead (chat stays available)."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline import open_app_markup
from bot.keyboards.menus import music_menu, photo_menu, video_menu
from bot.states import PhotoSG
from core.i18n import Translator, all_labels
from core.services import pricing

router = Router()


async def _section_off(message: Message, session: AsyncSession, name: str) -> bool:
    """Disabled section → show its editable "coming soon" text and return True so the
    caller stops (chat stays available)."""
    sec = await pricing.section_state(session, name)
    if not sec["enabled"]:
        await message.answer(sec["soon"])
        return True
    return False


# ----- /photo -----
@router.message(Command("photo"))
@router.message(F.text.in_(all_labels("btn.images")))
async def cmd_photo(
    message: Message, state: FSMContext, session: AsyncSession, _: Translator
) -> None:
    if await _section_off(message, session, "images"):
        return
    await state.set_state(PhotoSG.menu)
    await message.answer(_("photo.menu"), reply_markup=photo_menu(_))


# ----- /video -----
@router.message(Command("video"))
@router.message(F.text.in_(all_labels("btn.video")))
async def cmd_video(message: Message, session: AsyncSession, _: Translator) -> None:
    if await _section_off(message, session, "video"):
        return
    await message.answer(_("video.menu"), reply_markup=video_menu(_))


# ----- /music + /chirp alias -----
@router.message(Command("music", "chirp", "suno"))
@router.message(F.text.in_(all_labels("btn.music")))
async def cmd_music(message: Message, session: AsyncSession, _: Translator) -> None:
    if await _section_off(message, session, "music"):
        return
    await message.answer(_("music.menu"), reply_markup=music_menu(_))


# ----- Фотоэффекты reply button -> Mini App / coming soon -----
@router.message(F.text.in_(all_labels("btn.photo_effects")))
async def btn_photo_effects(message: Message, _: Translator) -> None:
    markup = open_app_markup(_)
    if markup:
        await message.answer(_("video.effects_hint"), reply_markup=markup)
    else:
        await message.answer(_("common.coming_soon"))


# photo services -> handlers/photo.py · video -> handlers/kling.py + video.py ·
# music -> handlers/music_gen.py  (no stub here, or it would shadow them)
