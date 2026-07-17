"""Read-replica scaffolding (2c): get_read_session routes to a replica when
DATABASE_READ_URL is set, and transparently falls back to the primary engine when
it is not — so nothing changes until a replica is provisioned. In the test env no
replica is configured, so the reader MUST be the primary and read sessions MUST
work against it.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import text

from core.db import (
    ReadSessionFactory,
    SessionFactory,
    engine,
    get_read_session,
    read_engine,
)
from core.models import Base


@pytest_asyncio.fixture(autouse=True)
async def _tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


def test_reader_falls_back_to_primary_when_no_replica():
    # No DATABASE_READ_URL in the test env → reader is the primary (no-op).
    assert read_engine is engine
    assert ReadSessionFactory is SessionFactory


@pytest.mark.asyncio
async def test_get_read_session_yields_working_session():
    gen = get_read_session()
    session = await gen.__anext__()
    try:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar() == 1
    finally:
        await gen.aclose()
