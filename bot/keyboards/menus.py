"""Service menu inline keyboards for /photo, /video, /music (§15.4–15.6)."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from core.i18n import Translator

# (label, service-key) — order matches the live menus. Labels prefixed with
# "srv." are i18n keys (translatable words); brand names stay literal.
PHOTO_SERVICES = [
    ("srv.photoeffects", "photoeffects"),
    ("🍌 Nano Banana Pro", "nano_banana"),
    ("🖼 GPT Image 2", "gpt_image2"),
    ("🌱 Seedream 5", "seedream"),
    ("🎨 Midjourney", "midjourney"),
    ("✏️ FLUX 2", "flux2"),
    ("🎯 Recraft", "recraft"),
    ("srv.avatar", "avatar"),
    ("srv.faceswap", "faceswap"),
    ("srv.upscale", "upscale"),
]

VIDEO_SERVICES = [
    ("srv.videoeffects", "videoeffects"),
    ("📊 Seedance 2.0", "seedance"),
    ("🌿 Veo 3.1", "veo"),
    ("⚡ Grok Imagine", "grok"),
    ("✨ Kling AI", "kling_ai"),
    ("🎭 Minimax Hailuo", "hailuo"),
    ("💃 Kling Motion", "kling_motion"),
    ("🌊 Kling Effects", "kling_effects"),
    ("☁ Pika 2.5", "pika"),
    ("🎨 Midjourney Video", "mj_video"),
]

MUSIC_SERVICES = [
    ("🎸 Suno", "suno"),
    ("💎 Lyria", "lyria"),
]


def _grid(items, prefix: str, _: Translator, per_row: int = 2) -> InlineKeyboardMarkup:
    rows, row = [], []
    for label, key in items:
        text = _(label) if label.startswith("srv.") else label
        row.append(InlineKeyboardButton(text=text, callback_data=f"{prefix}:{key}"))
        if len(row) == per_row:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text=_("btn.close"), callback_data="close")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def photo_menu(_: Translator) -> InlineKeyboardMarkup:
    return _grid(PHOTO_SERVICES, "photo", _)


def video_menu(_: Translator) -> InlineKeyboardMarkup:
    return _grid(VIDEO_SERVICES, "video", _)


def music_menu(_: Translator) -> InlineKeyboardMarkup:
    return _grid(MUSIC_SERVICES, "music", _)
