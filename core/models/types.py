"""Portable column types.

Keep native PostgreSQL types in production (JSONB, native UUID) but degrade to
portable equivalents on SQLite so the bot can run / be integration-tested with
zero external infra (in-memory dev mode)."""
from __future__ import annotations

from sqlalchemy import JSON, BigInteger, Integer, Uuid
from sqlalchemy.dialects.postgresql import JSONB

# JSONB on Postgres, plain JSON on SQLite/others.
JSONType = JSONB().with_variant(JSON(), "sqlite")

# Native UUID on Postgres, CHAR(32) on SQLite — provided by SQLAlchemy's Uuid.
UUIDType = Uuid(as_uuid=True)

# Auto-increment surrogate PK. BIGSERIAL on Postgres; on SQLite a BIGINT PK is
# NOT the rowid alias, so it won't auto-assign — degrade to INTEGER so inserts
# get an auto-incrementing id in zero-infra dev/test mode.
BigIntPK = BigInteger().with_variant(Integer(), "sqlite")
