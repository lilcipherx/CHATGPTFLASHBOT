"""Audit-trail helper — every sensitive admin action is recorded (§11A.1)."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from core.models import AdminAuditLog


async def audit(
    session: AsyncSession,
    *,
    admin_id: int,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    ip: str | None = None,
    # FIX: M7 - allow callers to fold the audit insert into their own transaction so the
    # audit row commits atomically with the mutation it records (no crash-window where the
    # mutation landed but the audit didn't, or vice-versa)
    commit: bool = True,
) -> None:
    session.add(
        AdminAuditLog(
            admin_id=admin_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            before=before,
            after=after,
            ip=ip,
        )
    )
    if commit:
        await session.commit()
