"""Async SQLAlchemy engine + session factory.

Primary engine handles all writes + strongly-consistent reads. An optional read
replica (``DATABASE_READ_URL``) backs ``ReadSessionFactory`` / ``get_read_session``
so read-heavy, lag-tolerant endpoints (History, analytics dashboards, catalogs) can
offload the primary. When no replica is configured the reader IS the primary — a
transparent no-op — so nothing changes until a replica is provisioned.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from core.config import settings


def _make_engine(url: str) -> AsyncEngine:
    """Build an async engine with pooling tuned to the deployment target."""
    if url.startswith("sqlite"):
        # zero-infra dev / tests. NullPool: don't cache connections — the async test
        # runner (pytest-asyncio) gives each test a fresh event loop, and a pooled
        # aiosqlite connection bound to a previous, now-closed loop surfaces as a
        # sporadic, order-dependent OperationalError. A fresh connection per checkout
        # avoids the cross-loop binding entirely (SQLite is dev/test-only here).
        # ``timeout`` sets SQLite's busy handler so a connection that briefly overlaps
        # a just-disposed one (NullPool churn across per-test loops) WAITS for the file
        # lock instead of raising "database is locked".
        return create_async_engine(
            url, echo=False, poolclass=NullPool, connect_args={"timeout": 30},
        )
    if settings.db_pgbouncer:
        # PgBouncer (transaction pooling) owns the real server-side pool and
        # multiplexes many app connections onto a few Postgres ones, so the app must
        # NOT keep its own pool (NullPool) and MUST disable the asyncpg + SQLAlchemy
        # prepared-statement caches — server-side prepared statements break under
        # transaction pooling (they can land on a different backend mid-session).
        return create_async_engine(
            url,
            echo=False,
            poolclass=NullPool,
            connect_args={
                "statement_cache_size": 0,           # asyncpg client cache off
                "prepared_statement_cache_size": 0,  # SQLAlchemy-asyncpg cache off
            },
        )
    return create_async_engine(
        url,
        echo=False,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=settings.db_pool_recycle,
    )


# Primary: all writes + read-your-write consistency.
engine = _make_engine(settings.database_url)
SessionFactory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Read replica (optional). Falls back to the primary engine when unset so callers of
# get_read_session behave identically until a replica DSN is configured.
read_engine: AsyncEngine = (
    _make_engine(settings.database_read_url) if settings.database_read_url else engine
)
ReadSessionFactory = (
    SessionFactory
    if read_engine is engine
    else async_sessionmaker(read_engine, class_=AsyncSession, expire_on_commit=False)
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency / generic session provider (primary — read+write)."""
    async with SessionFactory() as session:
        yield session


async def get_read_session() -> AsyncIterator[AsyncSession]:
    """Read-only session provider for lag-tolerant, read-heavy endpoints. Routes to
    the read replica when ``DATABASE_READ_URL`` is set, else the primary. Do NOT
    write in a handler that depends on this — the replica is read-only and may lag
    the primary; use get_session for anything that reads its own write."""
    async with ReadSessionFactory() as session:
        yield session
