"""Maintenance-mode middleware (ТЗ §8/§9).

When maintenance is enabled in the live business-config, every non-admin update is
answered with the maintenance message and dropped (handlers don't run). Admins
(settings.admin_ids) always pass through so they can keep operating the bot during
a maintenance window. Registered after BanMiddleware so a banned user is still
handled by the ban path first.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery, TelegramObject  # FIX: B6

from core.services import pricing
from core.services.users import is_admin


class MaintenanceMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("user")
        session = data.get("session")
        # Admins bypass; without a user/session we can't decide → let it through.
        if user is not None and is_admin(user.user_id):  # FIX: AUDIT-171 - removed dead session-None branch
            return await handler(event, data)
        try:
            state = await pricing.maintenance(session)
        except Exception:  # noqa: BLE001
            # FIX: AUDIT-13 - fail-CLOSED: if we can't read maintenance state, assume ON
            import structlog
            structlog.get_logger().error("maintenance.state_read_failed — failing closed")
            state = {"enabled": True, "message": "Service temporarily unavailable"}
        if not state["enabled"]:
            return await handler(event, data)

        msg = state["message"]
        if isinstance(event, Message):
            await event.answer(msg)
        elif isinstance(event, CallbackQuery):
            await event.answer(msg, show_alert=True)
        elif isinstance(event, PreCheckoutQuery):  # FIX: B6 - block payments during maintenance
            await event.answer(ok=False, error_message=msg)
        return None
