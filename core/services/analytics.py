"""Usage logging for analytics / antifraud (usage_log).

FIX: MISC - `log_action` was dead code (no callers in non-test code). Removed;
callers should use `session.add(UsageLog(...))` directly with their own commit
discipline, or the billing/promos/referrals helpers that already log usage
events with the right transaction semantics.
"""
from __future__ import annotations

# Intentionally empty: this module is kept as a placeholder so existing
# `from core.services import analytics` imports do not break, but no function
# is exported. Remove the module entirely once no imports remain.
