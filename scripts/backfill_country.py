"""Backfill User.country from the shared phone number where it's missing.

    python -m scripts.backfill_country [--dry-run]

country is normally derived at contact-share time (bot/handlers/account.py) via
core.services.notifications.country_from_phone. Users who shared a phone before that
logic — or whose phone resolved under the old, smaller calling-code map — may have a
phone but a NULL/empty country. This one-off pass recomputes country for exactly
those rows (phone present, country empty) and never overwrites an existing country.
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import or_, select

from core.db import SessionFactory
from core.models import User
from core.services.notifications import country_from_phone


async def main(dry_run: bool) -> None:
    updated = 0
    scanned = 0
    async with SessionFactory() as session:
        rows = (await session.scalars(
            select(User).where(
                User.phone.isnot(None), User.phone != "",
                or_(User.country.is_(None), User.country == ""),
            )
        )).all()
        for u in rows:
            scanned += 1
            cc = country_from_phone(u.phone)
            if cc:
                if not dry_run:
                    u.country = cc
                updated += 1
        if not dry_run:
            await session.commit()
    mode = "DRY-RUN — would update" if dry_run else "Updated"
    print(f"{mode} {updated} of {scanned} phone-bearing users without a country.")


if __name__ == "__main__":
    asyncio.run(main("--dry-run" in sys.argv))
