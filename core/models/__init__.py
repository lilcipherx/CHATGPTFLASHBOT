"""SQLAlchemy models — import all so Alembic autogenerate sees the full metadata."""
from core.models.admin import AdminAuditLog, AdminUser
from core.models.ai_routing import AIAccount, AIModel
from core.models.base import Base
from core.models.billing import (
    Broadcast,
    CheckoutIntent,
    GenerationJob,
    PaymentMethod,
    Pricing,
    PromoCode,
    Transaction,
)
from core.models.bot_instance import BotInstance
from core.models.catalog import (
    ChannelGate,
    CustomButtonStat,
    KlingEffectTemplate,
    KlingMotionTemplate,
    MiniAppBanner,
    MiniAppPhotoEffect,
    MiniAppVideoEffect,
    Referral,
    UsageLog,
)
from core.models.channel_post import ChannelPost
from core.models.contest import Contest, ContestEntry
from core.models.cron import CronJob
from core.models.crm import UserNote, UserTag
from core.models.feedback import Complaint, MessageFeedback
from core.models.gallery import GalleryItem
from core.models.gift import Gift
from core.models.support import SupportMessage
from core.models.user import PackBalance, User

__all__ = [
    "Base",
    "User",
    "PackBalance",
    "Transaction",
    "GenerationJob",
    "PaymentMethod",
    "Pricing",
    "PromoCode",
    "CheckoutIntent",
    "Broadcast",
    "KlingEffectTemplate",
    "KlingMotionTemplate",
    "MiniAppPhotoEffect",
    "MiniAppVideoEffect",
    "MiniAppBanner",
    "ChannelGate",
    "CustomButtonStat",
    "Referral",
    "UsageLog",
    "AdminUser",
    "AdminAuditLog",
    "AIAccount",
    "AIModel",
    "Gift",
    "MessageFeedback",
    "Complaint",
    "UserNote",
    "UserTag",
    "SupportMessage",
    "GalleryItem",
    "Contest",
    "ContestEntry",
    "ChannelPost",
    "BotInstance",
    "CronJob",
]
