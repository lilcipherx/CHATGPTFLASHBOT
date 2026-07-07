"""Admin-controllable scheduled jobs (the "beat" scheduler).

Each row is one cron job. The beat scheduler ticks every job once a minute, but this
row decides whether it actually runs: ``enabled`` turns it on/off and
``interval_seconds`` sets how often it may run (a tick is skipped until that much time
has passed since ``last_run_at``). Both are editable from the admin panel at runtime —
no redeploy needed. See core.services.cron_control (the gate) and workers.main (the
tick + wrapper).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin


class CronJob(Base, TimestampMixin):
    __tablename__ = "cron_jobs"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    interval_seconds: Mapped[int] = mapped_column(Integer, default=3600)
    # When the job last actually ran (used to enforce the interval + shown in admin).
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Short outcome of the last run ("ok" / truncated error) for the admin panel.
    last_status: Mapped[str | None] = mapped_column(String(200))
