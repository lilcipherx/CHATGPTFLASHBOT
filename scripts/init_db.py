"""Dev convenience: create all tables directly (use Alembic in prod).

    python -m scripts.init_db
"""
from __future__ import annotations

import asyncio

from core.db import engine
from core.models import Base


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ All tables created.")


if __name__ == "__main__":
    asyncio.run(main())
