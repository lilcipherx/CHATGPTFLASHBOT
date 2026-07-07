"""Тесты сервиса авто-отчётов (core.services.reports) — ТЗ §8.

Прямой прогон compute/render против реальной SQLite-сессии (паттерн
tests/test_admins): схема создаётся фикстурой через Base.metadata, данные
сеются через SessionFactory.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base, GenerationJob, Transaction, UsageLog, User
from core.services import reports


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


def _now() -> datetime:
    return datetime.now(UTC)


async def _user(session, user_id: int, created_at: datetime | None = None) -> User:
    u = User(user_id=user_id, created_at=created_at or _now())
    session.add(u)
    await session.commit()
    return u


async def _paid_tx(session, user_id: int, amount: int, currency: str = "stars",
                   created_at: datetime | None = None) -> None:
    session.add(Transaction(
        tx_id=uuid.uuid4(), user_id=user_id, product="credits", amount=amount,
        currency=currency, gateway="stars", status="paid",
        created_at=created_at or _now(),
    ))
    await session.commit()


async def test_empty_db_zeroes():
    async with SessionFactory() as s:
        data = await reports.compute_report(s, days=1)
        assert data.revenue_total == 0
        assert data.new_users == 0
        assert data.total_users == 0
        assert data.paid_users == 0
        assert data.avg_dau == 0.0
        assert data.arpu == 0.0
        assert data.conversion_pct == 0.0
        # Рендер не падает на пустых данных.
        text = reports.render_report_text(data)
        assert "Отчёт" in text
        assert "нет платежей" in text


async def test_revenue_and_currency_breakdown():
    async with SessionFactory() as s:
        await _user(s, 1)
        await _user(s, 2)
        await _paid_tx(s, 1, 100, "stars")
        await _paid_tx(s, 1, 50, "stars")
        await _paid_tx(s, 2, 200, "rub")
        # Неоплаченная транзакция в выручку не попадает.
        s.add(Transaction(
            tx_id=uuid.uuid4(), user_id=2, product="credits", amount=999,
            currency="stars", gateway="stars", status="pending",
        ))
        await s.commit()

        data = await reports.compute_report(s, days=1)
        assert data.revenue_total == 350
        assert data.revenue_by_currency == {"stars": 150, "rub": 200}
        assert data.paid_users == 2
        assert data.total_users == 2
        assert data.conversion_pct == 100.0
        assert data.arpu == 175.0
        assert data.arppu == 175.0


async def test_new_users_only_in_window():
    async with SessionFactory() as s:
        await _user(s, 1, created_at=_now())
        # Пользователь, созданный 10 дней назад, вне суточного окна для new_users,
        # но входит в total_users.
        await _user(s, 2, created_at=_now() - timedelta(days=10))
        data = await reports.compute_report(s, days=1)
        assert data.new_users == 1
        assert data.total_users == 2


async def test_dau_counts_distinct_users_per_day():
    async with SessionFactory() as s:
        await _user(s, 1)
        await _user(s, 2)
        # Пользователь 1 активен через usage_log И generation_job — считается один раз.
        s.add(UsageLog(user_id=1, action="chat"))
        s.add(GenerationJob(job_id=uuid.uuid4(), user_id=1, service="image",
                            status="complete"))
        s.add(UsageLog(user_id=2, action="chat"))
        await s.commit()
        await _paid_tx(s, 2, 10)

        data = await reports.compute_report(s, days=1)
        # Сегодня активны двое уникальных пользователей.
        assert data.avg_dau == 2.0
        assert len(data.dau_by_day) == 1


async def test_render_contains_metrics_and_csv():
    async with SessionFactory() as s:
        await _user(s, 1)
        await _paid_tx(s, 1, 500, "stars")
        data = await reports.compute_report(s, days=7)

        text = reports.render_report_text(data)
        assert "Выручка" in text
        assert "500" in text
        assert "ARPU" in text
        assert "за 7 дн." in text

        csv_out = reports.render_report_csv(data)
        assert "metric;value" in csv_out
        assert "revenue_total;500" in csv_out
        assert "revenue_stars;500" in csv_out


async def test_build_report_text_shortcut():
    async with SessionFactory() as s:
        await _user(s, 1)
        text = await reports.build_report_text(s, days=1)
        assert "Отчёт за сутки" in text
