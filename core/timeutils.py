"""Small datetime helpers shared across services."""
from __future__ import annotations

from datetime import UTC, datetime


def ensure_aware(dt: datetime) -> datetime:
    """Treat a naive datetime as UTC.

    SQLite round-trips ``DateTime(timezone=True)`` columns as naive while Postgres
    returns aware ones. Normalising here keeps age math, comparisons and
    ``isoformat()`` consistent across both, instead of every module hand-rolling the
    same ``dt if dt.tzinfo else dt.replace(tzinfo=UTC)`` one-liner.
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
