"""Static catalogs derived verbatim from the reverse-engineering report.

Models, pricing tiers, generation-cost multipliers and pack definitions. Prices
default here but are overridable via the `pricing` DB table without a redeploy.
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_MODEL = "gemini_3_1_flash"
DEFAULT_VOICE = "alloy"


@dataclass(frozen=True)
class TextModel:
    key: str
    name: str
    provider: str            # openai | anthropic | google | deepseek
    cost: int                # generations consumed per request
    premium: bool
    desc: str


# §5.1 — text models in /model (order matches the live keyboard)
TEXT_MODELS: list[TextModel] = [
    TextModel("gpt_5_5", "GPT-5.5", "openai", 3, True,
              "Новая топ-модель OpenAI. Каждый запрос расходует 3 генерации."),
    TextModel("gpt_5_4", "GPT-5.4", "openai", 1, True,
              "Универсальная модель для кодинга и работы с текстами."),
    TextModel("gpt_5_mini", "GPT-5 mini", "openai", 1, False,
              "Быстрая модель для повседневных вопросов."),
    TextModel("claude_4_8_opus", "Claude 4.8 Opus", "anthropic", 5, True,
              "Топ-модель Anthropic. Каждый запрос расходует 5 генераций."),
    TextModel("claude_4_6_sonnet", "Claude 4.6 Sonnet", "anthropic", 1, True,
              "Модель для текстов, кодинга и математики."),
    TextModel("deepseek_v4_pro", "DeepSeek V4 Pro", "deepseek", 1, True,
              "Топ-модель DeepSeek для сложных задач."),
    TextModel("deepseek_v4", "DeepSeek V4", "deepseek", 1, False,
              "Быстрая и мощная модель от китайского разработчика."),
    TextModel("gemini_3_5_flash", "Gemini 3.5 Flash", "google", 1, True,
              "Топ-модель Google."),
    TextModel("gemini_3_1_flash", "Gemini 3.1 Flash", "google", 1, False,
              "Мощная и быстрая рассуждающая модель Google."),
]

TEXT_MODELS_BY_KEY = {m.key: m for m in TEXT_MODELS}
FREE_MODEL_KEYS = {m.key for m in TEXT_MODELS if not m.premium}

# §9.4 — OpenAI TTS voices (Premium)
VOICES_FEMALE = ["ballad", "coral", "marin", "nova", "sage", "shimmer", "verse"]
VOICES_MALE = ["alloy", "ash", "cedar", "echo", "fable"]
ALL_VOICES = VOICES_MALE + VOICES_FEMALE

# §9.5 — interface languages
LANGUAGES = [
    ("en", "🇬🇧 English"),
    ("ru", "🇷🇺 Русский"),
    ("uz", "🇺🇿 O'zbekcha"),
    ("es", "🇪🇸 Español"),
    ("fr", "🇫🇷 Français"),
    ("ar", "🇸🇦 العربية"),
    ("pt", "🇧🇷 Português (Brasil)"),
    ("zh", "🇨🇳 简体中文"),
]
SUPPORTED_LOCALES = [code for code, _ in LANGUAGES]

# §11 — pricing (Telegram Stars). Keyed for the `pricing` table override.
SUBSCRIPTION_PRICES = {
    "premium":     {1: 600, 3: 1200, 6: 2000, 12: 3000},
    "premium_x2":  {1: 900, 3: 1800, 6: 3000, 12: 4500},
}

PACK_PRICES = {
    "image_pack": {50: 250, 100: 450, 200: 800, 500: 1750},
    "video_pack": {2: 150, 10: 500, 20: 900, 50: 2000},
    "music_pack": {20: 250, 50: 500, 100: 900},
}

# semantic label tokens -> localized via i18n keys pack.label.{token}
PACK_LABELS = {
    "image_pack": {200: "popular", 500: "best"},
    "video_pack": {20: "popular", 50: "best"},
    "music_pack": {50: "popular", 100: "best"},
}

AVATAR_PRICE = 200  # ⭐ one-time (/ava)

# 🪙 reward granted to a referrer on the referred user's first paid purchase.
REFERRAL_REWARD_CREDITS = 50

# 🪙 Credit top-up packs (qty -> Telegram Stars price). Overridable via pricing.
CREDIT_PACKS = {100: 250, 500: 1000, 1000: 1800}

# Mini App effect costs once the weekly free quota is exhausted (§23F).
# Per Q11, 🪙 credits are equivalent to image-pack credits.
MINIAPP_PHOTO_COST = {"1k": 2, "2k": 3, "4k": 4}
MINIAPP_VIDEO_COST = 1
MINIAPP_PHOTO_CATEGORIES = ["all", "female", "male", "children", "couple"]
# §23B — aspect-ratio options on the Фотоэффект create screen (cost is unaffected)
MINIAPP_PHOTO_RATIOS = [
    "auto", "1:1", "3:2", "2:3", "4:3", "3:4", "4:5", "5:4", "9:16", "16:9", "21:9",
]
MINIAPP_VIDEO_CATEGORIES = ["all", "dance", "emotion", "effect", "transform"]

DURATION_LABELS = {1: "Месяц", 3: "3 мес", 6: "6 мес", 12: "Год"}

# Payment gateways offered in step 3 of the purchase FSM
GATEWAYS = [
    ("stars", "⭐ Telegram Stars"),
    ("sbp_tribute", "💳 СБП"),
    ("yookassa", "💰 YooKassa"),
    ("stripe", "🌍 Stripe"),
    ("crypto", "🪙 Крипта"),
]

# Service "Инструкция" link slots surfaced inside photo/video service sub-menus
# (§15A). The URLs themselves are admin-set in business_config "doc_links" (empty by
# default — no third-party links ship); these are just the known keys a service spec
# can reference via doc_link_key, used to render the admin editor.
DOC_LINK_KEYS = ("banana", "gpt_images", "midjourney", "veo")
