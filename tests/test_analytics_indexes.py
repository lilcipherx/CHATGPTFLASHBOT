"""Index topology for the §8 analytics window queries.

The revenue/DAU dashboards filter transactions by (status, created_at) and usage_log
by created_at on every load. Assert the supporting composite/range indexes exist and
that the standalone transactions(status) index was dropped as redundant (its role is
subsumed by the composite's leading column). Guards migration
0023_analytics_window_indexes.
"""
from __future__ import annotations

from core.models import Transaction, UsageLog


def _index_columns(model) -> list[list[str]]:
    return [list(ix.columns.keys()) for ix in model.__table__.indexes]


def test_transactions_has_status_created_composite():
    cols = _index_columns(Transaction)
    assert ["status", "created_at"] in cols


def test_transactions_status_only_index_removed():
    # The composite already serves status-only lookups; a standalone one is redundant.
    cols = _index_columns(Transaction)
    assert ["status"] not in cols


def test_usage_log_created_at_indexed():
    cols = _index_columns(UsageLog)
    assert any(c == ["created_at"] for c in cols)
