"""Admin: DM any user via the bot + support inbox (ТЗ §7).

Three audited, support-gated endpoints:

* POST /messaging/users/{user_id}/message — cold-DM a user through the bot.
* GET  /messaging/support/inbox          — list open (unhandled) inbound messages.
* POST /messaging/support/{message_id}/reply — reply to an inbound message and
  mark it handled.

Telegram delivery goes through the shared Bot (core.bot_client.get_bot). A send
failure (user blocked the bot, never started it, …) is returned as
``{ok: false, error}`` rather than a 500 — the admin should see *why* it failed.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.audit import audit
from api.admin.deps import require_role
from core.bot_client import get_bot
from core.db import get_session
from core.models import AdminUser
from core.services import support

router = APIRouter(prefix="/messaging", tags=["admin-messaging"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


class MessageBody(BaseModel):
    # FIX: AUDIT13-M9 - cap DM length (Telegram rejects >4096 chars).
    text: str = Field(..., max_length=4096)


async def _send(user_id: int, text: str) -> tuple[bool, str | None]:
    """Deliver a message via the bot, returning (ok, error)."""
    try:
        await get_bot().send_message(user_id, text)
    except Exception as exc:  # noqa: BLE001 — surface any delivery failure to the admin
        return False, str(exc)
    return True, None


@router.post("/users/{user_id}/message")
async def message_user(
    user_id: int,
    body: MessageBody,
    request: Request,
    admin: AdminUser = Depends(require_role("support")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Send a cold DM to ``user_id`` via the bot; record it as an outbound message."""
    ok, error = await _send(user_id, body.text)
    if not ok:
        # FIX: F33 - audit the FAILED DM attempt so a failed cold-DM leaves a forensics
        # trail (was: returned {ok: False} with no audit row). Body is redacted per H5.
        await audit(
            session, admin_id=admin.id, action="support.message_user_failed",
            target_type="user", target_id=str(user_id),
            after={"text_redacted": True, "error": (error or "")[:200]}, ip=_ip(request),
        )
        return {"ok": False, "error": error}
    await support.record_outbound(session, user_id, admin.id, body.text)
    # FIX: H5 - never write the DM body into the audit log (it may contain private
    # user correspondence). The action + target_id + admin is enough for forensics;
    # the full text is preserved in support.outbound rows for authorized review.
    await audit(
        session, admin_id=admin.id, action="support.message_user",
        target_type="user", target_id=str(user_id),
        after={"text_redacted": True, "len": len(body.text)}, ip=_ip(request),
    )
    return {"ok": True}


@router.get("/support/inbox")
async def support_inbox(
    admin: AdminUser = Depends(require_role("support")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Open inbox: inbound, unhandled messages, newest first."""
    rows = await support.list_open(session)
    return [
        {
            "id": m.id,
            "user_id": m.user_id,
            "text": m.text,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in rows
    ]


@router.post("/support/{message_id}/reply")
async def support_reply(
    message_id: int,
    body: MessageBody,
    request: Request,
    admin: AdminUser = Depends(require_role("support")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Reply to an inbound message: deliver via the bot, record the outbound row,
    and mark the original inbound message handled."""
    from core.models.support import SupportMessage

    inbound = await session.get(SupportMessage, message_id)
    if inbound is None or inbound.direction != "in":
        raise HTTPException(status_code=404, detail="message not found")

    ok, error = await _send(inbound.user_id, body.text)
    if not ok:
        # FIX: F33 - audit the FAILED reply (same rationale as message_user).
        await audit(
            session, admin_id=admin.id, action="support.reply_failed",
            target_type="support_message", target_id=str(message_id),
            after={"text_redacted": True, "error": (error or "")[:200]}, ip=_ip(request),
        )
        return {"ok": False, "error": error}
    await support.record_outbound(session, inbound.user_id, admin.id, body.text)
    await support.mark_handled(session, message_id)
    # FIX: H5 - same rationale: don't store the reply body in audit_log.
    await audit(
        session, admin_id=admin.id, action="support.reply",
        target_type="support_message", target_id=str(message_id),
        after={"text_redacted": True, "len": len(body.text)}, ip=_ip(request),
    )
    return {"ok": True}
