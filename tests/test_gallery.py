"""Public gallery with moderation (ТЗ §4).

Service-level tests (submit / moderation / public listing) plus the admin
moderation endpoint coroutines called directly, mirroring test_business_admin."""
from __future__ import annotations

import types

import pytest
import pytest_asyncio

from api.admin import gallery as admin_gallery
from core.db import SessionFactory, engine
from core.models import AdminAuditLog, AdminUser, Base, User
from core.models.gallery import GalleryItem
from core.services import gallery
from core.services.admin_auth import hash_password
from core.services.moderation import ModerationResult


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


def _req():
    return types.SimpleNamespace(client=None)


async def _user(session, user_id=1) -> User:
    u = User(user_id=user_id, language_code="ru")
    session.add(u)
    await session.commit()
    return u


async def _admin(session, role="moderator") -> AdminUser:
    a = AdminUser(email="m@x.io", password_hash=hash_password("x"), role=role, is_active=True)
    session.add(a)
    await session.commit()
    return a


async def test_submit_creates_pending_item():
    async with SessionFactory() as s:
        await _user(s)
        item = await gallery.submit(s, 1, "https://cdn/x.png", "a cat")
        assert item.id is not None
        assert item.status == "pending"
        assert item.user_id == 1
        assert item.image_url == "https://cdn/x.png"
        assert item.prompt == "a cat"


async def test_disallowed_prompt_is_rejected(monkeypatch):
    async def _deny(_text: str) -> ModerationResult:
        return ModerationResult(False, "own_rules")

    monkeypatch.setattr(gallery.moderation, "moderate", _deny)
    async with SessionFactory() as s:
        await _user(s)
        with pytest.raises(gallery.ModerationRejected):
            await gallery.submit(s, 1, "https://cdn/x.png", "bad prompt")
        # No item should have been created.
        rows = await gallery.pending_list(s)
        assert rows == []


async def test_submit_without_prompt_skips_moderation(monkeypatch):
    async def _boom(_text: str) -> ModerationResult:
        raise AssertionError("moderation must not run when there is no prompt")

    monkeypatch.setattr(gallery.moderation, "moderate", _boom)
    async with SessionFactory() as s:
        await _user(s)
        item = await gallery.submit(s, 1, "https://cdn/x.png", None)
        assert item.status == "pending"


async def test_public_list_shows_only_approved():
    async with SessionFactory() as s:
        await _user(s)
        pend = await gallery.submit(s, 1, "https://cdn/p.png", None)
        appr = await gallery.submit(s, 1, "https://cdn/a.png", None)
        await gallery.set_status(s, appr.id, "approved", admin_id=7)
        public = await gallery.public_list(s, limit=30, offset=0)
        ids = {i.id for i in public}
        assert appr.id in ids
        assert pend.id not in ids


async def test_set_status_approve_appears_in_public_list():
    async with SessionFactory() as s:
        await _user(s)
        item = await gallery.submit(s, 1, "https://cdn/x.png", None)
        assert await gallery.public_list(s) == []
        updated = await gallery.set_status(s, item.id, "approved", admin_id=99)
        assert updated.status == "approved"
        assert updated.moderated_by == 99
        public = await gallery.public_list(s)
        assert [i.id for i in public] == [item.id]


async def test_admin_list_by_status_tabs():
    """The admin /gallery/list endpoint returns items for each moderation status —
    powering the pending queue plus the approved/rejected history tabs."""
    async with SessionFactory() as s:
        await _user(s)
        admin = await _admin(s)
        a = await gallery.submit(s, 1, "https://cdn/a.png", None)
        b = await gallery.submit(s, 1, "https://cdn/b.png", None)
        c = await gallery.submit(s, 1, "https://cdn/c.png", None)
        await gallery.set_status(s, a.id, "approved", admin_id=admin.id)
        await gallery.set_status(s, b.id, "rejected", admin_id=admin.id)
        # c stays pending

        pend = await admin_gallery.list_items(status="pending", admin=admin, session=s)
        appr = await admin_gallery.list_items(status="approved", admin=admin, session=s)
        rej = await admin_gallery.list_items(status="rejected", admin=admin, session=s)
        bogus = await admin_gallery.list_items(status="nope", admin=admin, session=s)

    assert [i["id"] for i in pend] == [c.id]
    assert [i["id"] for i in appr] == [a.id]
    assert [i["id"] for i in rej] == [b.id]
    assert [i["id"] for i in bogus] == [c.id]   # unknown status → pending


async def test_set_status_unknown_item_returns_none():
    async with SessionFactory() as s:
        assert await gallery.set_status(s, 12345, "approved", admin_id=1) is None


async def test_set_status_invalid_status_raises():
    async with SessionFactory() as s:
        await _user(s)
        item = await gallery.submit(s, 1, "https://cdn/x.png", None)
        with pytest.raises(ValueError):
            await gallery.set_status(s, item.id, "garbage", admin_id=1)


async def test_admin_approve_endpoint_flips_status_and_audits():
    async with SessionFactory() as s:
        await _user(s)
        admin = await _admin(s, "moderator")
        item = await gallery.submit(s, 1, "https://cdn/x.png", None)
        out = await admin_gallery.approve_item(item.id, _req(), admin=admin, session=s)
        assert out["ok"] is True
        assert out["status"] == "approved"

        refreshed = await s.get(GalleryItem, item.id)
        assert refreshed.status == "approved"
        assert refreshed.moderated_by == admin.id

        from sqlalchemy import select as _select
        logs = (await s.scalars(
            _select(AdminAuditLog).where(AdminAuditLog.action == "gallery.approved")
        )).all()
        assert len(logs) == 1


async def test_admin_reject_endpoint_flips_status_and_audits():
    async with SessionFactory() as s:
        await _user(s)
        admin = await _admin(s, "moderator")
        item = await gallery.submit(s, 1, "https://cdn/x.png", None)
        out = await admin_gallery.reject(item.id, _req(), admin=admin, session=s)
        assert out["status"] == "rejected"

        from sqlalchemy import func, select
        n = await s.scalar(
            select(func.count()).select_from(AdminAuditLog)
            .where(AdminAuditLog.action == "gallery.rejected")
        )
        assert n == 1
        # A rejected item never appears in the public list.
        assert await gallery.public_list(s) == []


async def test_admin_approve_missing_item_404():
    from fastapi import HTTPException

    async with SessionFactory() as s:
        admin = await _admin(s, "moderator")
        with pytest.raises(HTTPException) as exc:
            await admin_gallery.approve_item(999, _req(), admin=admin, session=s)
        assert exc.value.status_code == 404


async def test_submit_endpoint_rate_limited(monkeypatch):
    """/gallery/submit must be rate-limited: without a guard a user could spam submit,
    burning moderation cost (an AI call per prompt) and flooding the review queue."""
    from fastapi import HTTPException

    from api.routers import gallery as gallery_router
    from core.services import ratelimit

    async def _deny(_key, _limit, _window):
        return False

    monkeypatch.setattr(ratelimit, "allow", _deny)

    async with SessionFactory() as s:
        await _user(s, user_id=42)
        req = gallery_router.SubmitRequest(image_url="https://cdn/x.png", prompt="a cat")
        tg = {"id": 42, "username": "u", "language_code": "ru"}
        with pytest.raises(HTTPException) as exc:
            await gallery_router.submit_item(req, tg=tg, session=s)
        assert exc.value.status_code == 429
        # And nothing was written to the queue.
        assert await gallery.pending_list(s) == []


async def _owned_job(session, user_id: int, result_url: str):
    from core.models import GenerationJob

    job = GenerationJob(
        user_id=user_id, service="photoeffect", model_variant="nano_banana",
        params={"prompt": "x"}, status="complete", cost_credits=0, pack_type=None,
        result_url=result_url,
    )
    session.add(job)
    await session.commit()
    return job


async def test_submit_endpoint_allows_own_image(monkeypatch):
    """Under the limit, submitting an image the user actually generated creates a
    pending item (guard is not a wall)."""
    from api.routers import gallery as gallery_router
    from core.services import ratelimit

    async def _ok(_key, _limit, _window):
        return True

    monkeypatch.setattr(ratelimit, "allow", _ok)

    async with SessionFactory() as s:
        await _user(s, user_id=43)
        await _owned_job(s, 43, "https://cdn/x.png")
        req = gallery_router.SubmitRequest(image_url="https://cdn/x.png", prompt=None)
        tg = {"id": 43, "username": "u", "language_code": "ru"}
        out = await gallery_router.submit_item(req, tg=tg, session=s)
        assert out["status"] == "pending"


async def test_submit_endpoint_rejects_unowned_image(monkeypatch):
    """A user may not submit an arbitrary URL or another user's generated result."""
    from fastapi import HTTPException

    from api.routers import gallery as gallery_router
    from core.services import ratelimit

    async def _ok(_key, _limit, _window):
        return True

    monkeypatch.setattr(ratelimit, "allow", _ok)

    async with SessionFactory() as s:
        await _user(s, user_id=44)
        await _user(s, user_id=45)
        # This result belongs to user 45, not the submitter (44).
        await _owned_job(s, 45, "https://cdn/victim.png")
        req = gallery_router.SubmitRequest(image_url="https://cdn/victim.png", prompt=None)
        tg = {"id": 44, "username": "u", "language_code": "ru"}
        with pytest.raises(HTTPException) as exc:
            await gallery_router.submit_item(req, tg=tg, session=s)
        assert exc.value.status_code == 403
        assert await gallery.pending_list(s) == []
