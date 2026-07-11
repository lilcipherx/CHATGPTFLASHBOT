"""Seed template catalogs: Kling Effects (74), Kling Motion (13), gate channel.

    python -m scripts.seed_catalogs
"""
from __future__ import annotations

import asyncio

from sqlalchemy import delete

from core.config import settings
from core.db import SessionFactory
from core.models import (
    ChannelGate,
    KlingEffectTemplate,
    KlingMotionTemplate,
    MiniAppPhotoEffect,
    MiniAppVideoEffect,
)

# §21A — all 74 Kling Effects across 7 pages (paired left|right per row)
KLING_EFFECTS_PAGES = [
    ["Теннисный тренд", "Гонщик F1", "Футболист", "Корейский бейсбол", "Китайский тренд",
     "Свободное падение", "Фейерверк 2026", "Смешение цветов", "Маска лошади",
     "Плюшевая лошадка", "Рэп Вайбс", "Заморозка"],
    ["Воспоминания года", "Вязаный мир", "Кадры 2025", "Рождественский момент", "Ёлочный шар",
     "Рождественский дуэт", "Читающий мысли", "Магический плащ", "Имбирный пряник",
     "Вращающиеся карты", "Космический лифт", "Замедление времени"],
    ["Киносъёмка", "Приближение", "Отдаление", "Мур-р-друзья", "Вчера", "Зиплайн в джунглях",
     "Дезинтеграция", "Базовая модель", "Сквозь кадр", "Парашют", "Сладость или гадость",
     "Хэллоуин-образ"],
    ["Хэллоуин-погоня", "Дух-защитник", "Полёт к Земле", "Бейсбол", "Внутренний голос",
     "Образ суперзвезды", "Воздушный акробат", "Поехали!", "Неожиданная любовь",
     "Волшебная метла", "Батут", "Губки бантиком"],
    ["Сердце руками", "Воздушный поцелуй", "Выходи за меня!", "Угадай, что", "Похищение",
     "Сёрфинг", "Скейт", "Плеск воды", "Ракета", "Фетр-фетр", "Прыг-скок", "Плюшевая стрижка"],
    ["Желейный", "Крылья фантазии", "Пиксельный", "Празднование", "Выпускной альбом",
     "Полароид", "Аниме-фигурка", "Драка", "Сердечко руками", "Цветение", "Головокружение",
     "Пушистик"],
    ["Моти-моти", "Бум-бум"],
]

# §21A / §23E — Kling Motion dance & motion templates
KLING_MOTION = [
    "Тот самый танец", "Краш", "Color Mix", "Китайский тренд", "Эмодзи-челлендж",
    "Love You", "Врум-Врум", "Шаолинь", "Шаффл", "Кунг-фу Мастер", "Кемусан",
    "Бег", "Поппинг", "Майкл Джексон", "Футболист", "Корейский бейсбол",
    "Спокойный танец", "Спагетти", "Грустный молодой", "Я красивая", "Танцуй",
    "Сделай реальным", "Безумно влюблён", "Выстрел Купидона", "Люблю себя", "Демусан",
]
NEW_EFFECTS = {"Вчера"}

# English labels for the Kling templates (effects + motion). Stored in name_i18n so
# non-Russian users see English instead of raw Russian (resolver: name_i18n[locale]
# → name_i18n["en"] → name_ru). Keyed by the Russian name; covers both catalogs.
KLING_EN = {
    "Теннисный тренд": "Tennis Trend", "Гонщик F1": "F1 Racer", "Футболист": "Footballer",
    "Корейский бейсбол": "Korean Baseball", "Китайский тренд": "Chinese Trend",
    "Свободное падение": "Free Fall", "Фейерверк 2026": "Fireworks 2026",
    "Смешение цветов": "Color Mix", "Маска лошади": "Horse Mask", "Плюшевая лошадка": "Plush Pony",
    "Рэп Вайбс": "Rap Vibes", "Заморозка": "Freeze", "Воспоминания года": "Memories of the Year",
    "Вязаный мир": "Knitted World", "Кадры 2025": "2025 Frames",
    "Рождественский момент": "Christmas Moment", "Ёлочный шар": "Christmas Bauble",
    "Рождественский дуэт": "Christmas Duet", "Читающий мысли": "Mind Reader",
    "Магический плащ": "Magic Cloak", "Имбирный пряник": "Gingerbread",
    "Вращающиеся карты": "Spinning Cards", "Космический лифт": "Space Elevator",
    "Замедление времени": "Time Slowdown", "Киносъёмка": "Movie Shot", "Приближение": "Zoom In",
    "Отдаление": "Zoom Out", "Мур-р-друзья": "Purr Friends", "Вчера": "Yesterday",
    "Зиплайн в джунглях": "Jungle Zipline", "Дезинтеграция": "Disintegration",
    "Базовая модель": "Base Model", "Сквозь кадр": "Through the Frame", "Парашют": "Parachute",
    "Сладость или гадость": "Trick or Treat", "Хэллоуин-образ": "Halloween Look",
    "Хэллоуин-погоня": "Halloween Chase", "Дух-защитник": "Guardian Spirit",
    "Полёт к Земле": "Flight to Earth", "Бейсбол": "Baseball", "Внутренний голос": "Inner Voice",
    "Образ суперзвезды": "Superstar Look", "Воздушный акробат": "Aerial Acrobat",
    "Поехали!": "Let's Go!", "Неожиданная любовь": "Unexpected Love",
    "Волшебная метла": "Magic Broom", "Батут": "Trampoline", "Губки бантиком": "Pouty Lips",
    "Сердце руками": "Heart Hands", "Воздушный поцелуй": "Blow a Kiss",
    "Выходи за меня!": "Marry Me!", "Угадай, что": "Guess What", "Похищение": "Abduction",
    "Сёрфинг": "Surfing", "Скейт": "Skate", "Плеск воды": "Water Splash", "Ракета": "Rocket",
    "Фетр-фетр": "Felt Style", "Прыг-скок": "Hop-Skip", "Плюшевая стрижка": "Plush Haircut",
    "Желейный": "Jelly", "Крылья фантазии": "Wings of Fantasy", "Пиксельный": "Pixelated",
    "Празднование": "Celebration", "Выпускной альбом": "Yearbook", "Полароид": "Polaroid",
    "Аниме-фигурка": "Anime Figure", "Драка": "Fight", "Сердечко руками": "Finger Heart",
    "Цветение": "Bloom", "Головокружение": "Dizziness", "Пушистик": "Fluffy",
    "Моти-моти": "Mochi-Mochi", "Бум-бум": "Boom-Boom",
    # motion
    "Тот самый танец": "That Dance", "Краш": "Crush", "Color Mix": "Color Mix",
    "Эмодзи-челлендж": "Emoji Challenge", "Love You": "Love You", "Врум-Врум": "Vroom-Vroom",
    "Шаолинь": "Shaolin", "Шаффл": "Shuffle", "Кунг-фу Мастер": "Kung-Fu Master",
    "Кемусан": "Kemusan", "Бег": "Running", "Поппинг": "Popping",
    "Майкл Джексон": "Michael Jackson", "Спокойный танец": "Calm Dance", "Спагетти": "Spaghetti",
    "Грустный молодой": "Sad Young", "Я красивая": "I'm Beautiful", "Танцуй": "Dance",
    "Сделай реальным": "Make it Real", "Безумно влюблён": "Madly in Love",
    "Выстрел Купидона": "Cupid's Shot", "Люблю себя": "Love Myself", "Демусан": "Demusan",
}


def _kling_i18n(name: str) -> dict:
    """name_i18n payload for a Kling template: an English label when we have one."""
    en = KLING_EN.get(name)
    return {"en": en} if en else {}

# ---- Higgsfield-style effect presets (§ Mini App redesign) -----------------
# A preset is a style wrapper over a PHOTO_SPECS / VIDEO_SPECS service. Keys in
# `recommended`/`compat` are spec keys; `params` are that spec's defaults.

VIDEO_COMPAT = ["kling_ai", "veo", "hailuo", "pika"]
_KLING = {"model": "3.0", "duration": 5, "ratio": "9:16", "audio": True}
_VEO = {"model": "veo_3_1_fast", "ratio": "9:16"}
_HAILUO = {"model": "fast", "duration": 5, "res": "768P", "enhance": True}
_PIKA = {"duration": 5, "res": "720p", "ratio": "9:16"}

# (name, category, recommended, params, prompt_template, trending, author, badge)
MINIAPP_VIDEO = [
    ("Storm Giant", "effect", "kling_ai", _KLING,
     "Turn the subject into a colossal giant made of storm clouds and lightning, "
     "cinematic, dramatic volumetric light. {prompt}", True, "buralqy", "new"),
    ("Dragon Fantasy", "effect", "kling_ai", _KLING,
     "Epic fantasy scene, the subject rides a giant dragon over a burning sky. {prompt}",
     True, "buralqy", "top"),
    ("Explosion VFX", "effect", "kling_ai", _KLING,
     "Massive cinematic explosion behind the subject, sparks and debris, slow motion. {prompt}",
     False, None, None),
    ("Datamosh", "transform", "kling_ai", _KLING,
     "Glitchy datamosh transition, pixel smearing and digital artifacts. {prompt}",
     False, None, "new"),
    ("Cyber Morph", "transform", "veo", _VEO,
     "The subject morphs into a glowing cyborg, neon circuitry, futuristic. {prompt}",
     True, None, None),
    ("Anime Transform", "transform", "kling_ai", _KLING,
     "Transform the subject into a 2D anime character, vibrant cel shading. {prompt}",
     False, None, None),
    ("Neon Dance", "dance", "hailuo", _HAILUO,
     "The subject performs an energetic dance under neon club lights. {prompt}",
     False, None, None),
    ("K-Pop Move", "dance", "kling_ai", _KLING,
     "The subject dances a sharp synchronized K-pop choreography on a bright stage. {prompt}",
     True, None, "top"),
    ("Slow-Mo Walk", "dance", "pika", _PIKA,
     "Confident slow-motion runway walk, wind in the hair, cinematic. {prompt}",
     False, None, None),
    ("Cry to Smile", "emotion", "pika", _PIKA,
     "The subject's expression shifts gently from sadness to a bright smile. {prompt}",
     False, None, None),
    ("Surprised", "emotion", "veo", _VEO,
     "The subject reacts with genuine surprise and delight. {prompt}",
     False, None, None),
    ("Joy Burst", "emotion", "kling_ai", _KLING,
     "The subject bursts into joyful laughter, confetti falling around. {prompt}",
     True, None, None),
]

PHOTO_COMPAT = ["nano_banana", "seedream", "flux2"]
_NB = {"model": "nb2", "quality": "1k", "count": 1}
_SD = {"model": "seedream_5", "quality": "2k", "ratio": "1:1"}
_FLUX = {"model": "flux2", "ratio": "1:1"}

# (name, category, recommended, params, max_photos, prompt_template, trending, author, badge)
MINIAPP_PHOTO = [
    ("Glamour Portrait", "female", "nano_banana", _NB, 4,
     "High-fashion glamour studio portrait, soft beauty lighting, flawless skin. {prompt}",
     True, "buralqy", "top"),
    ("2000's Paparazzi", "female", "nano_banana", _NB, 4,
     "Early-2000s paparazzi flash photo, candid, grainy, on-camera flash. {prompt}",
     True, "buralqy", "new"),
    ("Vintage Film", "female", "flux2", _FLUX, 1,
     "35mm vintage film portrait, warm grain, faded colors, retro mood. {prompt}",
     False, None, None),
    ("Anime Style", "female", "seedream", _SD, 4,
     "Turn the photo into a polished anime illustration, clean lineart. {prompt}",
     False, None, None),
    ("Studio Headshot", "male", "seedream", _SD, 4,
     "Professional corporate headshot, neutral backdrop, crisp studio light. {prompt}",
     True, None, "top"),
    ("Cyberpunk", "male", "flux2", _FLUX, 1,
     "Cyberpunk neon portrait, rain-soaked city, holographic signs. {prompt}",
     True, None, "new"),
    ("Black & White", "male", "seedream", _SD, 4,
     "Dramatic high-contrast black and white portrait, fine-art mono. {prompt}",
     False, None, None),
    ("Cartoon Avatar", "children", "nano_banana", _NB, 4,
     "Cute 3D cartoon avatar of the child, Pixar-style, soft lighting. {prompt}",
     False, None, None),
    ("Little Superhero", "children", "nano_banana", _NB, 4,
     "The child as a heroic comic-book superhero with a cape. {prompt}",
     True, None, "top"),
    ("Wedding Shot", "couple", "seedream", _SD, 4,
     "Elegant wedding photo of the couple, golden hour, romantic bokeh. {prompt}",
     True, None, "pro"),
    ("Polaroid", "couple", "nano_banana", _NB, 4,
     "Retro polaroid snapshot of the couple, white frame, soft flash. {prompt}",
     False, None, None),
    ("Old Photo Restore", "couple", "nano_banana", _NB, 4,
     "Restore and colorize an old damaged photo of the couple, sharp and clean. {prompt}",
     False, None, None),
]


async def main() -> None:
    # FIX: MISC - require explicit confirmation before the destructive wipe (the script
    # DELETES all Kling/effects rows first). Set CONFIRM=1 in the env to skip (automation).
    import os
    if os.environ.get("CONFIRM") != "1":
        ans = input(
            "This will DELETE and re-seed the Kling/effects catalogs. Type 'yes' to continue: ")
        if ans.strip().lower() != "yes":
            print("aborted")
            return
    async with SessionFactory() as session:
        await session.execute(delete(KlingEffectTemplate))
        await session.execute(delete(KlingMotionTemplate))
        await session.execute(delete(MiniAppPhotoEffect))
        await session.execute(delete(MiniAppVideoEffect))

        tid = 1
        for page_idx, names in enumerate(KLING_EFFECTS_PAGES, start=1):
            for pos, name in enumerate(names, start=1):
                session.add(KlingEffectTemplate(
                    template_id=tid, page=page_idx, position=pos,
                    name_ru=name, name_i18n=_kling_i18n(name),
                    is_new=name in NEW_EFFECTS,
                ))
                tid += 1

        for pos, name in enumerate(KLING_MOTION, start=1):
            session.add(KlingMotionTemplate(
                template_id=pos, page=1, position=pos, name_ru=name,
                name_i18n=_kling_i18n(name),
            ))

        for i, row in enumerate(MINIAPP_PHOTO, start=1):
            name, cat, recommended, params, max_photos, tmpl, trending, author, badge = row
            session.add(MiniAppPhotoEffect(
                effect_id=i, category=cat, name_ru=name, badge=badge,
                is_ad=False, gen_count=len(MINIAPP_PHOTO) - i,
                recommended_model=recommended, compatible_models=PHOTO_COMPAT,
                prompt_template=tmpl, default_params=params, max_photos=max_photos,
                is_trending=trending, enabled=True, author=author, sort_order=i,
            ))
        for i, row in enumerate(MINIAPP_VIDEO, start=1):
            name, cat, recommended, params, tmpl, trending, author, _badge = row
            session.add(MiniAppVideoEffect(
                effect_id=i, category=cat, name_ru=name, provider=recommended,
                gen_count=len(MINIAPP_VIDEO) - i,
                recommended_model=recommended, compatible_models=VIDEO_COMPAT,
                prompt_template=tmpl, default_params=params, max_photos=1,
                is_trending=trending, enabled=True, author=author, sort_order=i,
            ))

        if settings.gate_channel:
            session.add(ChannelGate(channel=settings.gate_channel, is_active=True))

        await session.commit()
    print(
        f"✅ Seeded {tid - 1} Kling effects + {len(KLING_MOTION)} motion + "
        f"{len(MINIAPP_PHOTO)} photo effects + {len(MINIAPP_VIDEO)} video effects."
    )


if __name__ == "__main__":
    asyncio.run(main())
