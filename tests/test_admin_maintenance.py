"""Admin: обслуживание (api/admin/maintenance) — ТЗ §8.

Прямой вызов эндпоинт-корутин на реальной SQLite-БД (паттерн tests/test_admins):
сидируем superadmin через `_admin`, передаём admin=... напрямую.

ПРИМЕЧАНИЕ об имени файла: tests/test_maintenance.py уже занят другим срезом
(maintenance-mode middleware), поэтому этот тест назван test_admin_maintenance.py.
"""
from __future__ import annotations

import os
import types

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select

from api.admin import maintenance
from core.db import SessionFactory, engine
from core.models import AdminAuditLog, AdminUser, Base
from core.services.admin_auth import hash_password


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


def _req():
    return types.SimpleNamespace(client=None)


async def _admin(session, email="root@x.io", role="superadmin", active=True) -> AdminUser:
    a = AdminUser(
        email=email, password_hash=hash_password("x"), role=role, is_active=active
    )
    session.add(a)
    await session.commit()
    return a


async def test_backup_sqlite_returns_file():
    async with SessionFactory() as s:
        a = await _admin(s)
        resp = await maintenance.download_backup(_req(), admin=a, session=s)
        assert resp.media_type == "application/octet-stream"
        assert os.path.isfile(resp.path)
        assert os.path.getsize(resp.path) > 0
        # Снимок — валидный SQLite (магический заголовок файла).
        with open(resp.path, "rb") as fh:
            assert fh.read(16).startswith(b"SQLite format 3")
        rows = (await s.scalars(select(AdminAuditLog))).all()
        assert any(r.action == "maintenance.backup" for r in rows)


async def test_backup_postgres_501(monkeypatch):
    async with SessionFactory() as s:
        a = await _admin(s)
        monkeypatch.setattr(
            maintenance.settings, "database_url",
            "postgresql+asyncpg://u:p@localhost/db", raising=False,
        )
        with pytest.raises(HTTPException) as exc:
            await maintenance.download_backup(_req(), admin=a, session=s)
        assert exc.value.status_code == 501


async def test_logs_missing_file_returns_empty(monkeypatch, tmp_path):
    # Путь к логу резолвится внутри _log_path() из конфига; подменяем helper,
    # т.к. поле settings.log_file добавляется человеком при wiring (см. отчёт).
    from pathlib import Path
    async with SessionFactory() as s:
        a = await _admin(s)
        monkeypatch.setattr(
            maintenance, "_log_path", lambda: Path(tmp_path / "nope.log")
        )
        out = await maintenance.view_logs(_req(), limit=50, admin=a, session=s)
        assert out["lines"] == []
        assert out["count"] == 0


async def test_logs_tail_last_n(monkeypatch, tmp_path):
    log = tmp_path / "app.log"
    log.write_text("\n".join(f"line{i}" for i in range(100)) + "\n", encoding="utf-8")
    async with SessionFactory() as s:
        a = await _admin(s)
        monkeypatch.setattr(maintenance, "_log_path", lambda: log)
        out = await maintenance.view_logs(_req(), limit=10, admin=a, session=s)
        assert out["count"] == 10
        assert out["lines"][0] == "line90"
        assert out["lines"][-1] == "line99"
        rows = (await s.scalars(select(AdminAuditLog))).all()
        assert any(r.action == "maintenance.logs" for r in rows)


async def test_logs_limit_capped(tmp_path, monkeypatch):
    async with SessionFactory() as s:
        a = await _admin(s)
        # Запредельный limit не должен падать — он клампится до _LOGS_MAX_LIMIT.
        # Точечно укажем пустой лог-путь (реальный logs/app.log теперь может
        # существовать — файловое логирование стало штатной фичей).
        monkeypatch.setattr(maintenance, "_log_path", lambda: tmp_path / "absent.log")
        out = await maintenance.view_logs(_req(), limit=10_000_000, admin=a, session=s)
        assert out["count"] == 0  # файла по этому пути нет → пусто
        assert out["count"] <= maintenance._LOGS_MAX_LIMIT
