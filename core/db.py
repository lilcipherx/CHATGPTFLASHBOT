"""Async SQLAlchemy engine + session factory."""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from core.config import settings

if settings.database_url.startswith("sqlite"):
    # zero-infra dev / tests. NullPool: don't cache connections — the async test
    # runner (pytest-asyncio) gives each test a fresh event loop, and a pooled
    # aiosqlite connection bound to a previous, now-closed loop surfaces as a
    # sporadic, order-dependent OperationalError. A fresh connection per checkout
    # avoids the cross-loop binding entirely (SQLite is dev/test-only here).
    # ``timeout`` sets SQLite's busy handler so a connection that briefly overlaps
    # a just-disposed one (NullPool churn across per-test loops) WAITS for the file
    # lock instead of raising "database is locked".
    engine = create_async_engine(
        settings.database_url, echo=False, poolclass=NullPool,
        connect_args={"timeout": 30},
    )
elif settings.db_pgbouncer:
    # PgBouncer (transaction pooling) owns the real server-side pool and
    # multiplexes many app connections onto a few Postgres ones, so the app must
    # NOT keep its own pool (NullPool) and MUST disable the asyncpg + SQLAlchemy
    # prepared-statement caches — server-side prepared statements break under
    # transaction pooling (they can land on a different backend mid-session).
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        poolclass=NullPool,
        connect_args={
            "statement_cache_size": 0,           # asyncpg client cache off
            "prepared_statement_cache_size": 0,  # SQLAlchemy-asyncpg cache off
        },
    )
else:
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=settings.db_pool_recycle,
    )

SessionFactory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency / generic session provider."""
    async with SessionFactory() as session:
        yield session
