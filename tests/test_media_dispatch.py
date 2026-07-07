"""Media dispatch: aggregator-account routing with fallback to the direct
provider, and account health on rate-limit (no network — fake gateway/provider)."""
from __future__ import annotations

import pytest_asyncio
from sqlalchemy import select

from core.ai_router.base import ImageResult, JobStatus
from core.db import SessionFactory, engine
from core.models import Base
from core.models.ai_routing import AIAccount, AIModel
from core.services import ai_routing as routing
from core.services.media_dispatch import (
    generate_image_routed,
    generate_image_routed_managed,
    resolve_backends,
    submit_first,
)


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


class _RateLimited(Exception):
    status_code = 429


class _FakeGateway:
    def __init__(self, *, submit_fail: bool = False, image_url: str = "https://gw/img.png"):
        self.submit_fail = submit_fail
        self.image_url = image_url

    def is_available(self) -> bool:
        return True

    async def submit(self, model, params) -> str:
        if self.submit_fail:
            raise _RateLimited()
        return "gw-task"

    async def poll(self, task_id) -> JobStatus:
        return JobStatus("complete", result_url="https://gw/out.mp4")

    async def generate_image(self, model, prompt, cfg) -> list[ImageResult]:
        return [ImageResult(url=self.image_url)]


class _FakeDirect:
    name = "kling"

    def is_available(self) -> bool:
        return True

    async def submit(self, params) -> str:
        return "direct-task"

    async def poll(self, task_id) -> JobStatus:
        return JobStatus("complete", result_url="https://direct/out.mp4")


async def _seed_video_model(s, *, account_kind=None):
    s.add(AIModel(key="kling_ai", title="Kling", upstream_model="kling-v2",
                  modality="video", account_kind=account_kind))
    s.add(AIAccount(name="kie1", kind="kie", base_url="https://api.kie.ai",
                    api_key="k", modality="video", tier=0))
    await s.commit()


async def test_resolve_backends_account_before_direct(monkeypatch):
    monkeypatch.setattr(routing, "gateway_for_account", lambda acc: _FakeGateway())
    async with SessionFactory() as s:
        await _seed_video_model(s)
        backends = await resolve_backends(
            s, modality="video", model_key="kling_ai", params={},
            direct_provider=_FakeDirect(),
        )
        assert [b.account_id is not None for b in backends] == [True, False]
        backend, task_id = await submit_first(s, backends)
        assert backend.account_id is not None and task_id == "gw-task"
        # the account that accepted the submit is marked healthy
        acc = (await s.scalars(select(AIAccount))).one()
        assert acc.status == "active" and acc.total_requests == 1


async def test_submit_falls_back_to_direct_on_429(monkeypatch):
    monkeypatch.setattr(routing, "gateway_for_account",
                        lambda acc: _FakeGateway(submit_fail=True))
    async with SessionFactory() as s:
        await _seed_video_model(s)
        backends = await resolve_backends(
            s, modality="video", model_key="kling_ai", params={},
            direct_provider=_FakeDirect(),
        )
        backend, task_id = await submit_first(s, backends)
        assert backend.account_id is None and task_id == "direct-task"  # direct fallback
        acc = (await s.scalars(select(AIAccount))).one()
        assert acc.status == "cooldown"  # rate-limited account sidelined


async def test_direct_only_when_no_model_configured():
    async with SessionFactory() as s:
        backends = await resolve_backends(
            s, modality="video", model_key="unknown", params={},
            direct_provider=_FakeDirect(),
        )
        assert len(backends) == 1 and backends[0].account_id is None


async def test_generate_image_routed_prefers_gateway(monkeypatch):
    monkeypatch.setattr(routing, "gateway_for_account",
                        lambda acc: _FakeGateway(image_url="https://gw/i.png"))

    async def _direct():
        return [ImageResult(url="https://direct/i.png")]

    async with SessionFactory() as s:
        s.add(AIModel(key="nb", title="NB", upstream_model="nano", modality="image"))
        s.add(AIAccount(name="kie-img", kind="kie", base_url="https://api.kie.ai",
                        api_key="k", modality="image", tier=0))
        await s.commit()
        out = await generate_image_routed(
            s, model_key="nb", prompt="p", cfg={}, direct_fn=_direct,
        )
        assert out[0].url == "https://gw/i.png"


async def test_generate_image_routed_direct_when_no_account():
    async def _direct():
        return [ImageResult(url="https://direct/i.png")]

    async with SessionFactory() as s:
        out = await generate_image_routed(
            s, model_key="missing", prompt="p", cfg={}, direct_fn=_direct,
        )
        assert out[0].url == "https://direct/i.png"


# ---- managed variant: holds NO session across the generation (M3) -----------
async def test_managed_prefers_gateway_and_marks_health(monkeypatch):
    monkeypatch.setattr(routing, "gateway_for_account",
                        lambda acc: _FakeGateway(image_url="https://gw/i.png"))

    async def _direct():
        return [ImageResult(url="https://direct/i.png")]

    async with SessionFactory() as s:
        s.add(AIModel(key="nb", title="NB", upstream_model="nano", modality="image"))
        s.add(AIAccount(name="kie-img", kind="kie", base_url="https://api.kie.ai",
                        api_key="k", modality="image", tier=0))
        await s.commit()

    # called WITHOUT a session — it manages its own short-lived ones
    out = await generate_image_routed_managed(
        model_key="nb", prompt="p", cfg={}, direct_fn=_direct,
    )
    assert out[0].url == "https://gw/i.png"

    async with SessionFactory() as s:
        acc = (await s.scalars(select(AIAccount))).one()
        assert acc.status == "active" and acc.total_requests == 1


async def test_managed_falls_back_to_direct_and_sidelines_account(monkeypatch):
    class _FailGateway:
        def is_available(self) -> bool:
            return True

        async def generate_image(self, model, prompt, cfg):
            raise _RateLimited()  # 429 → account goes to cooldown

    monkeypatch.setattr(routing, "gateway_for_account", lambda acc: _FailGateway())

    async def _direct():
        return [ImageResult(url="https://direct/i.png")]

    async with SessionFactory() as s:
        s.add(AIModel(key="nb", title="NB", upstream_model="nano", modality="image"))
        s.add(AIAccount(name="kie-img", kind="kie", base_url="https://api.kie.ai",
                        api_key="k", modality="image", tier=0))
        await s.commit()

    out = await generate_image_routed_managed(
        model_key="nb", prompt="p", cfg={}, direct_fn=_direct,
    )
    assert out[0].url == "https://direct/i.png"  # fell back to direct

    async with SessionFactory() as s:
        acc = (await s.scalars(select(AIAccount))).one()
        assert acc.status == "cooldown"  # rate-limited account sidelined


async def test_managed_direct_when_no_account():
    async def _direct():
        return [ImageResult(url="https://direct/i.png")]

    out = await generate_image_routed_managed(
        model_key="missing", prompt="p", cfg={}, direct_fn=_direct,
    )
    assert out[0].url == "https://direct/i.png"


# ---- admin kill-switch enforced by the media router ----
async def test_kill_switch_blocks_resolve_backends():
    """A disabled provider key yields no backends, so the worker refunds + fails
    instead of routing through a provider the admin turned off."""
    from core.services import providers_admin

    class _Direct:
        name = "direct"
        def is_available(self): return True
        async def submit(self, p): return "t"
        async def poll(self, t): return None

    async with SessionFactory() as s:
        # enabled by default -> direct provider present
        b1 = await resolve_backends(
            s, modality="video", model_key="kling_ai", params={}, direct_provider=_Direct())
        assert len(b1) == 1
        # kill it -> empty
        await providers_admin.toggle(s, "kling_ai")
        b2 = await resolve_backends(
            s, modality="video", model_key="kling_ai", params={}, direct_provider=_Direct())
        assert b2 == []


async def test_kill_switch_blocks_image_generation():
    import pytest

    from core.services import providers_admin
    from core.services.media_dispatch import generate_image_routed_managed

    async def _direct_fn():
        return [ImageResult(url="http://x/a.png")]

    async with SessionFactory() as s:
        await providers_admin.toggle(s, "nano_banana")  # disable
    with pytest.raises(RuntimeError):
        await generate_image_routed_managed(
            model_key="nano_banana", prompt="hi", cfg={}, direct_fn=_direct_fn)


async def test_list_providers_covers_all_modalities():
    """The Providers page lists video + image + music providers, each tagged with
    its modality (not just video)."""

    from api.admin.ops import list_providers
    from core.models import AdminUser

    async with SessionFactory() as s:
        s.add(AdminUser(email="p@x.io", password_hash="x", role="admin", is_active=True))
        await s.commit()
        admin = (await s.scalars(select(AdminUser))).first()
        out = await list_providers(admin=admin, session=s)
    mods = {p["modality"] for p in out}
    keys = {p["key"] for p in out}
    assert {"video", "image", "music"} <= mods
    assert {"kling_ai", "nano_banana", "suno"} <= keys  # one from each modality
    assert all("modality" in p and "available" in p and "disabled" in p for p in out)
