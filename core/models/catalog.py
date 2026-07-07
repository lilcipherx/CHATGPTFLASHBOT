"""Template catalogs (Kling effects/motion, Mini App photo/video effects),
channel gates, referrals and analytics."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base
from core.models.types import BigIntPK, JSONType


class _LocalizedName:
    """Resolver for catalog rows carrying a Russian name + a ``name_i18n`` JSON map
    ``{locale: name}``. Returns the locale's translation, else English, else the RU
    name — so non-Russian users get at least an English label, never raw Russian."""

    def localized_name(self, locale: str) -> str:
        if locale == "ru":
            return self.name_ru  # RU is canonical, stored in name_ru
        names = getattr(self, "name_i18n", None) or {}
        return names.get(locale) or names.get("en") or self.name_ru


class KlingEffectTemplate(_LocalizedName, Base):
    __tablename__ = "kling_effects_templates"

    template_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    page: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer)
    name_ru: Mapped[str] = mapped_column(String(100))
    name_i18n: Mapped[dict] = mapped_column(JSONType, default=dict)
    is_new: Mapped[bool] = mapped_column(Boolean, default=False)
    preview_url: Mapped[str | None] = mapped_column(String(500))


class KlingMotionTemplate(_LocalizedName, Base):
    __tablename__ = "kling_motion_templates"

    template_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    page: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer)
    name_ru: Mapped[str] = mapped_column(String(100))
    name_i18n: Mapped[dict] = mapped_column(JSONType, default=dict)
    preview_url: Mapped[str | None] = mapped_column(String(500))


class MiniAppPhotoEffect(_LocalizedName, Base):
    __tablename__ = "mini_app_photo_effects"

    effect_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(String(20))  # all|female|male|children|couple
    name_ru: Mapped[str] = mapped_column(String(100))
    name_i18n: Mapped[dict] = mapped_column(JSONType, default=dict)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500))
    badge: Mapped[str | None] = mapped_column(String(10))  # new|top|pro
    gen_count: Mapped[int] = mapped_column(Integer, default=0)
    is_ad: Mapped[bool] = mapped_column(Boolean, default=False)

    # Preset fields (Higgsfield-style create flow) — a style wrapper over a
    # PHOTO_SPECS service. All nullable/defaulted: additive migration.
    recommended_model: Mapped[str | None] = mapped_column(String(40))
    compatible_models: Mapped[list] = mapped_column(JSONType, default=list)
    prompt_template: Mapped[str | None] = mapped_column(Text)
    # How the Mini App treats the prompt field: hidden | optional | required.
    prompt_mode: Mapped[str] = mapped_column(
        String(10), default="optional", server_default="optional"
    )
    default_params: Mapped[dict] = mapped_column(JSONType, default=dict)
    max_photos: Mapped[int] = mapped_column(Integer, default=1)
    preview_url: Mapped[str | None] = mapped_column(String(500))
    is_trending: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    author: Mapped[str | None] = mapped_column(String(40))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    # Admin price override in 🪙 credits. 0 = use the model spec's computed cost.
    price: Mapped[int] = mapped_column(Integer, default=0)


class MiniAppVideoEffect(_LocalizedName, Base):
    __tablename__ = "mini_app_video_effects"

    effect_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(String(20))  # all|dance|emotion|effect|transform
    name_ru: Mapped[str] = mapped_column(String(100))
    name_i18n: Mapped[dict] = mapped_column(JSONType, default=dict)
    provider: Mapped[str] = mapped_column(String(20))  # kling|higgsfield|pika
    thumbnail_url: Mapped[str | None] = mapped_column(String(500))
    gen_count: Mapped[int] = mapped_column(Integer, default=0)
    is_ad: Mapped[bool] = mapped_column(Boolean, default=False)

    # Preset fields — a style wrapper over a VIDEO_SPECS service.
    recommended_model: Mapped[str | None] = mapped_column(String(40))
    compatible_models: Mapped[list] = mapped_column(JSONType, default=list)
    prompt_template: Mapped[str | None] = mapped_column(Text)
    # How the Mini App treats the prompt field: hidden | optional | required.
    prompt_mode: Mapped[str] = mapped_column(
        String(10), default="optional", server_default="optional"
    )
    default_params: Mapped[dict] = mapped_column(JSONType, default=dict)
    max_photos: Mapped[int] = mapped_column(Integer, default=1)
    preview_url: Mapped[str | None] = mapped_column(String(500))
    is_trending: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    author: Mapped[str | None] = mapped_column(String(40))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    # Admin price override in 🪙 credits. 0 = use the model spec's computed cost.
    price: Mapped[int] = mapped_column(Integer, default=0)


class MiniAppBanner(Base):
    """Carousel slide shown at the top of the Mini App. Fully admin-managed:
    image, optional caption + tap target, ordering and visibility. The rotation
    interval is a single global setting stored in the `pricing` KV table under
    key ``miniapp_carousel`` (see api.admin.banners / api.routers.miniapp)."""

    __tablename__ = "mini_app_banners"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    image_url: Mapped[str] = mapped_column(String(500))
    title: Mapped[str | None] = mapped_column(String(120))
    subtitle: Mapped[str | None] = mapped_column(String(200))
    link_url: Mapped[str | None] = mapped_column(String(500))  # deep link / effect open
    # Locale targeting: NULL = shown to every language; a 2-letter code = shown only
    # to users on that language (the carousel image carries baked-in text, so the
    # admin makes a per-language slide instead of translating an overlay).
    locale: Mapped[str | None] = mapped_column(String(8), default=None)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Lightweight engagement counters (no per-event table): the Mini App increments
    # these via /api/banners/{id}/impression|click; the admin derives CTR = clicks/impr.
    impressions: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    clicks: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class CustomButtonStat(Base):
    """Click counter for an admin-defined /links button (ТЗ §8). The buttons live
    in business_config.custom_buttons (a JSON list, not a table); this keyed-by the
    button's stable ``id`` row just accumulates taps recorded by the /r/{id} redirect
    tracker. The button's URL is always read live from the config, never stored here."""

    __tablename__ = "custom_button_stats"

    button_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    clicks: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    last_click_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChannelGate(Base):
    __tablename__ = "channel_gates"

    channel: Mapped[str] = mapped_column(String(50), primary_key=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Referral(Base):
    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    referrer_id: Mapped[int] = mapped_column(BigInteger, index=True)
    referred_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    reward_type: Mapped[str | None] = mapped_column(String(20))
    reward_amount: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    rewarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UsageLog(Base):
    __tablename__ = "usage_log"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    action: Mapped[str] = mapped_column(String(50))
    meta: Mapped[dict] = mapped_column(JSONType, default=dict)
    # Indexed: the §8 DAU/analytics window scans usage_log by created_at >= start.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
