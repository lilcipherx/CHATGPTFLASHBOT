"""Admin panel users + audit log (§11A)."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin
from core.models.types import BigIntPK, JSONType


class AdminUser(Base, TimestampMixin):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # FIX: AUDIT-1 - totp_secret now stores Fernet ciphertext (enc:: prefix)
    totp_secret: Mapped[str | None] = mapped_column(String(256))
    # FIX: AUDIT-B2 - map the 2FA recovery-codes column added by migration 0039
    # (was model/migration drift: the migration creates admin_users.backup_codes_hashed
    # but the model never declared it, so scripts.check_migrations flagged a
    # remove_column drift and the CI migrations gate went red). Stores up to 8 argon2-
    # hashed single-use backup codes (JSONB on Postgres, JSON on SQLite); nullable +
    # server_default '[]' exactly as the migration, so autogenerate sees no difference.
    backup_codes_hashed: Mapped[list | None] = mapped_column(
        JSONType, nullable=True, server_default="[]"
    )
    role: Mapped[str] = mapped_column(String(20), default="support")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Bumped on logout / password change to revoke all previously-issued tokens
    # (JWT carries this value as "ver"; a mismatch is rejected).
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(BigInteger, index=True)
    action: Mapped[str] = mapped_column(String(60))
    target_type: Mapped[str | None] = mapped_column(String(40))
    target_id: Mapped[str | None] = mapped_column(String(60))
    before: Mapped[dict | None] = mapped_column(JSONType)
    after: Mapped[dict | None] = mapped_column(JSONType)
    ip: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
