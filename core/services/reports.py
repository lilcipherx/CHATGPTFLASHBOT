"""Сервис авто-отчётов по расписанию (ТЗ §8).

Чистый DB-слой: считает агрегаты за период и рендерит человекочитаемый RU-текст
(и опционально CSV). Никакого Redis/бота здесь нет — это переиспользуется как
ARQ-задачей (workers.report_tasks), так и потенциально админ-API.

Метрики повторяют логику api.admin.analytics:
  * revenue — SUM(Transaction.amount) по оплаченным транзакциям за окно. Сумма
    в СМЕШАННЫХ единицах (звёзды + минорные единицы карточных шлюзов), поэтому
    дополнительно даётся разбивка по валютам — честное прочтение.
  * new_users — число User, созданных в окне.
  * DAU — DISTINCT пользователей с UsageLog ИЛИ GenerationJob ИЛИ оплаченной
    Transaction за день (прокси, как в analytics._dau); в отчёте берём среднее.
  * ARPU = revenue / total_users; ARPPU = revenue / paid_users;
    conversion = paid_users / total_users * 100.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import GenerationJob, Transaction, UsageLog, User


def _window_start(days: int) -> datetime:
    """Нижняя граница окна (включительно): начало первого календарного дня."""
    days = max(1, min(days, 365))
    start = datetime.now(UTC) - timedelta(days=days - 1)
    return start.replace(hour=0, minute=0, second=0, microsecond=0)


@dataclass(slots=True)
class ReportData:
    """Посчитанные метрики отчёта за период (готовы к рендеру)."""

    days: int
    period_start: datetime
    period_end: datetime
    revenue_total: int
    revenue_by_currency: dict[str, int] = field(default_factory=dict)
    new_users: int = 0
    total_users: int = 0
    paid_users: int = 0
    # DAU по дням (прокси) и усреднённое значение за период.
    dau_by_day: list[tuple[str, int]] = field(default_factory=list)
    avg_dau: float = 0.0
    arpu: float = 0.0
    arppu: float = 0.0
    conversion_pct: float = 0.0


async def compute_report(session: AsyncSession, days: int = 1) -> ReportData:
    """Посчитать агрегаты отчёта за последние ``days`` дней (по умолчанию сутки).

    Все агрегаты считаются в БД одним проходом на запрос, по образцу
    api.admin.analytics. Возвращает чистую структуру данных без сайд-эффектов.
    """
    start = _window_start(days)
    now = datetime.now(UTC)
    paid = (Transaction.status == "paid")
    in_window = (Transaction.created_at >= start)

    # --- Выручка ---
    revenue_total = await session.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(paid, in_window)
    ) or 0

    revenue_rows = (await session.execute(
        select(Transaction.currency, func.coalesce(func.sum(Transaction.amount), 0))
        .where(paid, in_window).group_by(Transaction.currency)
    )).all()
    revenue_by_currency = {c: int(s) for c, s in revenue_rows}

    # --- Пользователи ---
    new_users = await session.scalar(
        select(func.count()).select_from(User).where(User.created_at >= start)
    ) or 0
    total_users = await session.scalar(select(func.count()).select_from(User)) or 0
    paid_users = await session.scalar(
        select(func.count(func.distinct(Transaction.user_id))).where(paid, in_window)
    ) or 0

    # --- DAU (прокси: usage_log | generation_job | оплаченная транзакция) ---
    usage = select(
        UsageLog.user_id.label("user_id"),
        func.date(UsageLog.created_at).label("d"),
    ).where(UsageLog.created_at >= start)
    jobs = select(
        GenerationJob.user_id.label("user_id"),
        func.date(GenerationJob.created_at).label("d"),
    ).where(GenerationJob.created_at >= start)
    txs = select(
        Transaction.user_id.label("user_id"),
        func.date(Transaction.created_at).label("d"),
    ).where(paid, in_window)
    activity = union(usage, jobs, txs).subquery()
    dau_rows = (await session.execute(
        select(activity.c.d, func.count(func.distinct(activity.c.user_id)))
        .group_by(activity.c.d).order_by(activity.c.d)
    )).all()
    dau_by_day = [(str(d), int(n)) for d, n in dau_rows]
    avg_dau = round(sum(n for _, n in dau_by_day) / len(dau_by_day), 1) if dau_by_day else 0.0

    # --- Производные метрики ---
    revenue_total = int(revenue_total)
    arpu = round(revenue_total / total_users, 2) if total_users else 0.0
    arppu = round(revenue_total / paid_users, 2) if paid_users else 0.0
    conversion_pct = round(paid_users / total_users * 100, 2) if total_users else 0.0

    return ReportData(
        days=days,
        period_start=start,
        period_end=now,
        revenue_total=revenue_total,
        revenue_by_currency=revenue_by_currency,
        new_users=int(new_users),
        total_users=int(total_users),
        paid_users=int(paid_users),
        dau_by_day=dau_by_day,
        avg_dau=avg_dau,
        arpu=arpu,
        arppu=arppu,
        conversion_pct=conversion_pct,
    )


def render_report_text(data: ReportData) -> str:
    """Сформировать человекочитаемый RU-отчёт (HTML parse_mode для Telegram)."""
    period = data.days
    title = "за сутки" if period == 1 else f"за {period} дн."
    start = data.period_start.strftime("%d.%m.%Y")
    end = data.period_end.strftime("%d.%m.%Y %H:%M UTC")

    if data.revenue_by_currency:
        rev_lines = "\n".join(
            f"   • {cur}: {amount}" for cur, amount in sorted(data.revenue_by_currency.items())
        )
    else:
        rev_lines = "   • нет платежей"

    return (
        f"<b>📊 Отчёт {title}</b>\n"
        f"<i>{start} — {end}</i>\n\n"
        f"<b>💰 Выручка (смешанные единицы):</b> {data.revenue_total}\n"
        f"{rev_lines}\n\n"
        f"<b>👥 Пользователи</b>\n"
        f"   • новых: {data.new_users}\n"
        f"   • всего: {data.total_users}\n"
        f"   • платящих за период: {data.paid_users}\n"
        f"   • средний DAU: {data.avg_dau}\n\n"
        f"<b>📈 Метрики</b>\n"
        f"   • конверсия: {data.conversion_pct}%\n"
        f"   • ARPU: {data.arpu}\n"
        f"   • ARPPU: {data.arppu}"
    )


def render_report_csv(data: ReportData) -> str:
    """Отрендерить отчёт в CSV-строку (метрика;значение) для выгрузки/архива."""
    import csv
    import io

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["metric", "value"])
    writer.writerow(["period_days", data.days])
    writer.writerow(["period_start", data.period_start.isoformat()])
    writer.writerow(["period_end", data.period_end.isoformat()])
    writer.writerow(["revenue_total", data.revenue_total])
    for cur, amount in sorted(data.revenue_by_currency.items()):
        writer.writerow([f"revenue_{cur}", amount])
    writer.writerow(["new_users", data.new_users])
    writer.writerow(["total_users", data.total_users])
    writer.writerow(["paid_users", data.paid_users])
    writer.writerow(["avg_dau", data.avg_dau])
    writer.writerow(["conversion_pct", data.conversion_pct])
    writer.writerow(["arpu", data.arpu])
    writer.writerow(["arppu", data.arppu])
    return buf.getvalue()


async def build_report_text(session: AsyncSession, days: int = 1) -> str:
    """Удобный шорткат: посчитать и сразу отрендерить текстовый отчёт."""
    data = await compute_report(session, days=days)
    return render_report_text(data)
