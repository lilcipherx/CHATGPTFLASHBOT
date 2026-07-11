"""/account (§15.8) and the Account reply button."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline import account_keyboard
from core.config import settings
from core.constants import TEXT_MODELS_BY_KEY
from core.i18n import Translator, all_labels
from core.models import PackBalance, User
from core.services import loyalty, pricing
from core.services.notifications import country_from_phone
from core.services.quota import text_quota_state

router = Router()


def _vip_account_line(prog: dict | None, _: Translator) -> str:
    """One-line VIP status for /account, or '' when VIP is off. Shows the current
    tier + progress to the next (or 'max' at the top, or distance to the first tier)."""
    if prog is None:
        return ""
    current, nxt = prog["current"], prog["next"]
    if current is None and nxt is not None:
        return _("account.vip_none", next=nxt["name"], left=prog["to_next"])
    if current is not None and nxt is None:
        return _("account.vip_top", tier=current["name"])
    if current is not None and nxt is not None:
        return _("account.vip", tier=current["name"], next=nxt["name"], left=prog["to_next"])
    return ""


@router.message(F.contact)
async def on_contact(message: Message, session: AsyncSession, user: User, _: Translator) -> None:
    """Store the user's phone (+ derived country) when they share their OWN
    contact. A contact card for someone else is ignored for privacy."""
    contact = message.contact
    sender = message.from_user
    if contact is None or sender is None:
        return
    # Only store the user's OWN contact; a card shared for someone else is ignored.
    if contact.user_id and contact.user_id != sender.id:
        return
    user.phone = contact.phone_number
    user.country = country_from_phone(contact.phone_number) or user.country
    await session.commit()
    await message.answer(_("contact.saved"))


async def _render_account(
    message: Message, session: AsyncSession, user: User, _: Translator
) -> None:
    state = await text_quota_state(session, user)
    balances = await session.get(PackBalance, user.user_id)
    if user.sub_tier == "premium_x2" and user.is_premium:
        sub = _("account.sub_premium_x2")
    elif user.is_premium:
        sub = _("account.sub_premium")
    else:
        sub = _("account.sub_free")
    model = TEXT_MODELS_BY_KEY.get(user.selected_model)
    prog = await loyalty.progress(session, user)
    text = _(
        "account",
        used=state.used,
        limit=state.limit,
        credits=user.credits,
        sub=sub,
        model_name=model.name if model else user.selected_model,
        image=balances.image_credits if balances else 0,
        video=balances.video_credits if balances else 0,
        music=balances.music_credits if balances else 0,
        support=settings.support_contact,
    )
    vip_line = _vip_account_line(prog, _)
    if vip_line:
        text += "\n" + vip_line
    role_line = await _role_line(session, user, _)
    if role_line:
        text += "\n" + role_line
    await message.answer(text, reply_markup=account_keyboard(_, show_vip=prog is not None))


async def _role_line(session: AsyncSession, user: User, _: Translator) -> str:
    """A '🎭 Роль: …' line for /account when a persona/custom role is active, else ''.
    The active prompt is matched against the admin preset list to recover its title;
    a prompt that matches no preset is the user's own role (shown as «своя роль»)."""
    if not (user.role_enabled and user.custom_role):
        return ""
    for r in await pricing.preset_roles(session):
        if r["prompt"] == user.custom_role:
            return _("account.role", title=r["title"])
    return _("account.role", title=_("account.role_custom"))


@router.message(Command("account"))
async def cmd_account(message: Message, session: AsyncSession, user: User, _: Translator) -> None:
    await _render_account(message, session, user, _)


@router.message(F.text.in_(all_labels("btn.account")))
async def btn_account(message: Message, session: AsyncSession, user: User, _: Translator) -> None:
    await _render_account(message, session, user, _)


@router.callback_query(F.data == "vip:open")
async def cb_vip(callback: CallbackQuery, session: AsyncSession, user: User, _: Translator) -> None:
    """The full VIP ladder: every tier with its threshold + bonuses, the user's own
    tier marked. Shown only when VIP is enabled (else just acknowledge)."""
    # FIX: POLISH-12 - answer the callback IMMEDIATELY so the button's loading
    # spinner closes instantly. The previous code ran loyalty.progress() (a DB
    # query) before answering, leaving the button visibly "thinking" for 2-3s.
    await callback.answer()
    prog = await loyalty.progress(session, user)
    if prog is None:
        return
    current = prog["current"]
    lines = [_("vip.title", spent=prog["spent"])]
    for t in prog["tiers"]:
        mark = "✅" if current is not None and t["min_spent"] == current["min_spent"] else "▫️"
        lines.append(_(
            "vip.row", mark=mark, name=t["name"], min=t["min_spent"],
            daily=t["bonus_daily"], weekly=t["bonus_weekly"],
        ))
    if callback.message:
        await callback.message.answer("\n".join(lines))


# FIX: AUDIT13-M22 - GDPR Art. 20 self-service data export. Returns the user's own
# records as a downloadable JSON document.
@router.message(Command("export_data"))
async def cmd_export_data(
    message: Message, session: AsyncSession, user: User, _: Translator,
) -> None:
    import json

    from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
    from aiogram.types import BufferedInputFile

    from core.services.gdpr import export_user_data

    data = await export_user_data(session, user.user_id)
    blob = json.dumps(data, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    doc = BufferedInputFile(blob, filename=f"my_data_{user.user_id}.json")
    try:
        await message.answer_document(doc, caption=_("gdpr.export_ready"))
    except (TelegramForbiddenError, TelegramBadRequest):
        pass


# FIX: AUDIT13-L11 - the /delete_account prompt tells the user to type /cancel, but no
# such handler existed (falling through as unrecognised text). Register a no-op /cancel
# that clears any FSM state and acknowledges, so the advertised escape hatch works.
@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, _: Translator) -> None:
    await state.clear()
    await message.answer(_("common.cancelled"))


# FIX: AUDIT12-21 - GDPR Art. 17 self-service bot command. Two-step confirmation.
@router.message(Command("delete_account"))
async def cmd_delete_account(
    message: Message, session: AsyncSession, user: User, _: Translator,
) -> None:
    args = (message.text or "").split(maxsplit=1)
    confirm_token = args[1].strip().upper() if len(args) > 1 else ""
    if confirm_token != "CONFIRM":
        await message.answer(_("gdpr.delete_confirm_prompt", cancel_cmd="/cancel"))
        return
    from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

    from core.services.gdpr import delete_user_data
    user_id = user.user_id
    counts = await delete_user_data(session, user_id)
    await session.commit()
    try:
        await message.answer(_("gdpr.deleted", user_id=user_id))
    except (TelegramForbiddenError, TelegramBadRequest):
        pass
    import structlog
    structlog.get_logger().info("gdpr.user_self_deleted", user_id=user_id, counts=counts)
