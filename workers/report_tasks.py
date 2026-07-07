"""Cron-задача авто-отчётов по расписанию (ТЗ §8).

Считает админ-отчёт (выручка/DAU/новые пользователи/конверсия/ARPU) через чистый
DB-сервис core.services.reports и отправляет его в админ-чат через общий Bot
(core.bot_client). По форме повторяет workers.notify_tasks: ctx-точка входа,
обёрнутая в arq.cron, со своей сессией SessionFactory. Запускается на единственном
планировщике BeatSettings, поэтому отчёт уходит ровно один раз за тик.
"""
from __future__ import annotations

import structlog
from arq import cron

from core.config import settings
from core.db import SessionFactory
from core.services.reports import compute_report, render_report_text

log = structlog.get_logger()

# Период отчёта по умолчанию — сутки (ежедневный дайджест).
REPORT_DAYS = 1


def _target_chat_id() -> int | None:
    """Чат-получатель отчёта: явный settings.report_chat_id, иначе первый из
    admin_user_ids. None — если не настроен ни один (отчёт не отправляем)."""
    explicit = getattr(settings, "report_chat_id", 0) or 0
    if explicit:
        return int(explicit)
    admins = sorted(settings.admin_ids)
    return admins[0] if admins else None


async def _send_scheduled_report(ctx) -> dict[str, int | bool]:
    """Посчитать суточный отчёт и отправить его в админ-чат.

    Сервисный слой чистый (только БД); отправка использует общий Bot. Если
    чат-получатель не настроен, тихо выходим (не считаем агрегаты впустую).
    """
    chat_id = _target_chat_id()
    if chat_id is None:
        log.warning("report.skip_no_chat")
        return {"sent": False}

    async with SessionFactory() as session:
        data = await compute_report(session, days=REPORT_DAYS)
    text = render_report_text(data)

    from core.bot_client import get_bot

    try:
        await get_bot().send_message(chat_id, text, parse_mode="HTML")
    except Exception as exc:  # noqa: BLE001 — отчёт не должен ронять планировщик
        log.warning("report.send_failed", error=str(exc))
        return {"sent": False}

    log.info("report.sent", chat_id=chat_id, revenue=data.revenue_total,
             new_users=data.new_users)
    return {"sent": True, "new_users": data.new_users, "revenue": data.revenue_total}


# Ежедневно в 08:00 UTC — утренний дайджест по итогам прошедших суток.
send_scheduled_report = cron(_send_scheduled_report, hour=8, minute=0)
