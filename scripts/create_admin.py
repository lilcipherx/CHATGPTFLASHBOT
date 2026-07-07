"""Create (or update) an admin user and print its TOTP enrolment URI.

    python -m scripts.create_admin <email> <password> [role]

role: superadmin | admin | support | moderator   (default: superadmin)
Scan the printed otpauth:// URI in an authenticator app; the OTP is then
required at login.
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from core.db import SessionFactory
from core.models import AdminUser
from core.services.admin_auth import hash_password, new_totp_secret, totp_uri


async def main(email: str, password: str, role: str) -> None:
    # Store lowercased: login matches case-insensitively, so this prevents a
    # near-duplicate admin row differing only by email case.
    email = email.strip().lower()
    async with SessionFactory() as session:
        admin = await session.scalar(select(AdminUser).where(AdminUser.email == email))
        secret = new_totp_secret()
        if admin is None:
            admin = AdminUser(
                email=email, password_hash=hash_password(password),
                totp_secret=secret, role=role, is_active=True,
            )
            session.add(admin)
        else:
            admin.password_hash = hash_password(password)
            admin.totp_secret = secret
            admin.role = role
            admin.is_active = True
        await session.commit()

    print(f"✅ Admin '{email}' ({role}) saved.")
    print("Scan this in your authenticator app:")
    print(totp_uri(secret, email))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit("usage: python -m scripts.create_admin <email> <password> [role]")
    asyncio.run(main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "superadmin"))
