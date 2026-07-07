"""User lifecycle: upsert on /start, settings mutations, referral capture."""
from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.models.user import PackBalance, User


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def user_locale(session: AsyncSession, user_id: int) -> str:
    """The user's stored language (for localizing async worker notifications that
    have only a user_id), falling back to 'ru' when unknown/unset."""
    u = await session.get(User, user_id)
    return u.language_code if (u and u.language_code) else "ru"


def _normalize_lang(language_code: str | None) -> str:
    """Telegram's reported language as a clean base subtag for honest storage.

    We keep the user's ACTUAL language (e.g. "de", "hi") rather than coercing it to
    a supported UI locale — coercion fabricated data (every non-supported user looked
    like "ru"). Rendering stays safe because ``core.i18n.t`` falls back to RU for any
    unsupported/empty locale at render time. An absent language is stored as "" (not a
    guessed default), so analytics never invents a language the account never had.
    """
    return (language_code or "").strip().lower().split("-")[0][:5]


async def get_or_create_user(
    session: AsyncSession,
    user_id: int,
    username: str | None = None,
    language_code: str | None = None,
    referred_by: int | None = None,
    source: str | None = None,
    bot_id: int | None = None,
) -> tuple[User, bool]:
    """Returns (user, created)."""
    user = await session.get(User, user_id)
    if user is not None:
        if username and user.username != username:
            user.username = username
            await session.commit()
        return user, False

    user = User(
        user_id=user_id,
        username=username,
        # Real Telegram language (base subtag), or "" when Telegram reported none —
        # never a fabricated default. See _normalize_lang.
        language_code=_normalize_lang(language_code),
        # self-referral guard
        referred_by=referred_by if referred_by and referred_by != user_id else None,
        # first-touch traffic source, set once on creation (truncate to column len)
        source=source[:64] if source else None,
        # multi-bot tenant attribution (ТЗ §0), set once at signup
        bot_id=bot_id,
    )
    session.add(user)
    session.add(PackBalance(user_id=user_id))
    try:
        await session.commit()
    except IntegrityError:
        # Two concurrent first-touches (e.g. a fast double /start, or the bot and
        # the Mini App both registering at once) both saw no row and tried to
        # INSERT the same user_id PK. The loser hits the unique constraint here —
        # roll our duplicate back and return the row the winner committed.
        await session.rollback()
        existing = await session.get(User, user_id)
        if existing is not None:
            return existing, False
        raise  # not a duplicate-PK race — surface the real error

    # Welcome bonus (ТЗ §4): admin-configurable 🪙 grant for a brand-new user.
    # 0 = off (default). Best-effort — a config/grant hiccup must never block signup.
    try:
        from core.services import credits, pricing

        amount = (await pricing.promos(session)).get("welcome_bonus", 0)
        if amount > 0:
            await credits.grant(session, user, amount)
    except Exception:  # noqa: BLE001
        pass
    return user, True


async def set_model(session: AsyncSession, user: User, model_key: str) -> None:
    user.selected_model = model_key
    await session.commit()


async def set_language(session: AsyncSession, user: User, lang: str) -> None:
    user.language_code = lang
    await session.commit()


async def toggle_context(session: AsyncSession, user: User) -> bool:
    user.context_enabled = not user.context_enabled
    await session.commit()
    return user.context_enabled


async def set_role(session: AsyncSession, user: User, role: str | None) -> None:
    user.custom_role = role
    user.role_enabled = bool(role)
    await session.commit()


async def set_voice(
    session: AsyncSession, user: User, *, voice: str | None = None, enabled: bool | None = None
) -> None:
    if voice is not None:
        user.voice_name = voice
    if enabled is not None:
        user.voice_enabled = enabled
    await session.commit()


def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids
