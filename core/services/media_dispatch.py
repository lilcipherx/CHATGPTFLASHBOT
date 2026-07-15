"""Media generation dispatch: route a job through DB-configured aggregator
accounts (Kie/MuAPI/APIMart…) with automatic fallback to the direct env-key
provider — the same pool → fallback engine used for text, generalised to
image/video/music.

A worker asks for the ordered list of backends for a job; each backend is either
a media gateway (built from an AIAccount) or the direct provider. Account health
(cooldown on rate-limit, error counting) is updated as backends are tried, so a
throttled aggregator is skipped next time.

Backward-compatible: if the admin has not configured an AIModel/account for a
service, the only backend returned is the direct provider — i.e. exactly today's
behaviour.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from core.ai_router.base import ImageResult, JobStatus
from core.models.ai_routing import AIAccount
from core.services import ai_routing as routing

# Upstream statuses meaning "this account is out" → cooldown instead of hard error.
_EXHAUSTED_STATUSES = {401, 402, 403, 429}


def _status_code(exc: Exception) -> int | None:
    code = getattr(exc, "status_code", None)
    if code is None:
        resp = getattr(exc, "response", None)
        code = getattr(resp, "status_code", None)
    return code


async def _mark_failure(session, account_id: int, exc: Exception) -> None:
    acc = await session.get(AIAccount, account_id)
    if acc is None:
        return
    # FIX: AI-19 - sanitize the exception string before persisting it to
    # AIAccount.last_error so aggregator 401/403 errors (which echo the
    # Authorization header) don't leak API keys into the admin-visible field.
    from core.ai_router.registry import _sanitize_exc
    safe = _sanitize_exc(exc)
    if _status_code(exc) in _EXHAUSTED_STATUSES:
        await routing.mark_exhausted(session, acc, error=safe)
    else:
        await routing.mark_error(session, acc, safe)


@dataclass
class Backend:
    """A submit/poll backend: a media gateway account, or the direct provider
    (account_id is None for direct)."""

    name: str
    account_id: int | None
    submit: Callable[[], Awaitable[str]]
    poll: Callable[[str], Awaitable[JobStatus]]
    # FIX: AUDIT-G1 - the routed model's admin-set per-request cost, carried with the
    # backend so submit_first can accrue account spend (feeds the spend-limit cap).
    # 0 for the direct env provider (not spend-tracked).
    cost_micros: int = 0


async def resolve_backends(
    session, *, modality: str, model_key: str, params: dict, direct_provider
) -> list[Backend]:
    """Ordered backends to try for a submit/poll job (video/music): configured
    aggregator accounts first (pool → fallback), then the direct env provider.

    Returns [] when the admin kill-switch has disabled this provider key, so the
    worker refunds + fails instead of generating through a provider the admin turned
    off (the Providers-page switch is enforced here, not just displayed)."""
    from core.services import providers_admin

    if await providers_admin.is_disabled(session, model_key):
        return []
    backends: list[Backend] = []
    model = await routing.resolve_model(session, model_key)
    if model is not None and model.modality == modality:
        upstream = model.upstream_model
        for acc in await routing.resolve_route(session, model):
            gw = routing.gateway_for_account(acc)
            if gw is None or not gw.is_available():
                continue
            backends.append(
                Backend(
                    name=f"{acc.kind}#{acc.id}",
                    account_id=acc.id,
                    submit=lambda gw=gw, m=upstream: gw.submit(m, params),
                    poll=lambda tid, gw=gw: gw.poll(tid),
                    cost_micros=model.cost_micros or 0,  # FIX: AUDIT-G1
                )
            )
    if direct_provider is not None and direct_provider.is_available():
        backends.append(
            Backend(
                name=getattr(direct_provider, "name", "direct"),
                account_id=None,
                submit=lambda: direct_provider.submit(params),
                poll=lambda tid: direct_provider.poll(tid),
            )
        )
    return backends


async def has_backend(session, *, modality: str, model_key: str, direct_provider) -> bool:
    """True when a generation for (modality, model_key) has at least one usable backend
    — a configured gateway account (via the AIModel catalog) OR an available direct
    provider, and the provider key is not admin-disabled. Reuses resolve_backends so
    the pre-charge availability check matches what the worker will actually try."""
    backends = await resolve_backends(
        session, modality=modality, model_key=model_key, params={},
        direct_provider=direct_provider,
    )
    return bool(backends)


async def submit_first(session, backends: list[Backend]) -> tuple[Backend | None, str | None]:
    """Submit to each backend in order; return (backend, task_id) for the first
    that accepts. Marks account health on success/failure. (None, None) if all
    backends fail — the caller then refunds and fails the job."""
    for b in backends:
        try:
            task_id = await b.submit()
        except Exception as exc:  # noqa: BLE001 — classify + try the next backend
            if b.account_id is not None:
                # FIX: F12 - _mark_failure wrapped so a DB hiccup doesn't abort the
                # pool→fallback loop (the whole point of submit_first).
                try:
                    await _mark_failure(session, b.account_id, exc)
                except Exception:  # noqa: BLE001 — health-stat failure is non-fatal
                    pass
            continue
        if b.account_id is not None:
            # FIX: R18 - mark_success must NOT abort the success path on its own failure
            # (a DB hiccup recording health stats shouldn't discard an accepted task).
            # The task_id is the contract; wrap health-update so it degrades to a log.
            try:
                acc = await session.get(AIAccount, b.account_id)
                if acc is not None:
                    await routing.mark_success(session, acc, cost_micros=b.cost_micros)
            except Exception:  # noqa: BLE001 — health-stat failure is non-fatal
                pass
        return b, task_id
    return None, None


async def submit_or_resume(
    session, backends: list[Backend], *, existing_provider_job_id: str | None,
    existing_backend: str | None = None,
) -> tuple[Backend | None, str | None]:
    """Submit to the first accepting backend — OR, if this job was already submitted
    by a previous attempt (``existing_provider_job_id`` set), RESUME polling that
    task via the backend that ORIGINALLY submitted it instead of submitting again.

    This is what makes an ARQ retry safe: a worker that crashed after submitting
    must not create a second (charged) provider task. The owning backend is
    identified by ``existing_backend`` (its ``name``, persisted at submit time): in
    a multi-backend pool we must poll the SAME backend that holds the task, not a
    peer that would only ever report 'processing'/unknown and force a needless
    timeout refund of an already-completed, paid job.

    Falls back to the first backend when no owner is recorded (legacy jobs from
    before owner-tracking). ``(None, None)`` when no usable backend is available —
    e.g. the owning backend is no longer in the pool — so the caller refunds rather
    than polling the wrong provider."""
    if existing_provider_job_id:
        if existing_backend:
            for b in backends:
                if b.name == existing_backend:
                    return b, existing_provider_job_id
            return None, None  # owning backend gone — can't safely resume
        for b in backends:  # legacy job without a recorded owner
            return b, existing_provider_job_id
        return None, None
    return await submit_first(session, backends)


async def generate_image_routed(
    session, *, model_key: str, prompt: str, cfg: dict,
    direct_fn: Callable[[], Awaitable[list[ImageResult]]],
) -> list[ImageResult]:
    """Image generation through aggregator accounts (image modality) first, then
    the direct adapter. `direct_fn` is an async callable producing the existing
    env-key result, so behaviour is unchanged when no account is configured.

    NOTE: holds the given session across the (slow) provider call. Workers should
    use ``generate_image_routed_managed`` instead so they don't tie up a pooled
    DB connection during generation."""
    model = await routing.resolve_model(session, model_key)
    if model is not None and model.modality == "image":
        for acc in await routing.resolve_route(session, model):
            gw = routing.gateway_for_account(acc)
            if gw is None or not gw.is_available():
                continue
            try:
                images = await gw.generate_image(model.upstream_model, prompt, cfg)
            except Exception as exc:  # noqa: BLE001 — try the next account / direct
                # FIX: F12 - _mark_failure must not abort the fallback loop on its own
                # DB hiccup; wrap it so a health-stat failure degrades to a log.
                try:
                    await _mark_failure(session, acc.id, exc)
                except Exception:  # noqa: BLE001 — health-stat failure is non-fatal
                    pass
                continue
            # FIX: F11 - mark_success must NOT abort the success path on its own failure
            # (a DB hiccup recording health stats shouldn't discard already-fetched
            # images). Mirror the R18 wrap in submit_first.
            try:
                await routing.mark_success(session, acc, cost_micros=model.cost_micros or 0)
            except Exception:  # noqa: BLE001 — health-stat failure is non-fatal
                pass
            return images
    return await direct_fn()


async def generate_image_routed_managed(
    *, model_key: str, prompt: str, cfg: dict,
    direct_fn: Callable[[], Awaitable[list[ImageResult]]],
) -> list[ImageResult]:
    """Same routing as ``generate_image_routed`` but holds NO DB connection during
    the (slow) provider HTTP call. Route resolution and per-account health updates
    each use a short-lived session; the generation runs between them.

    Use this from workers so a long image generation never ties up a pooled
    connection — the image-modality analogue of the video/music workers that
    submit+poll outside their session."""
    from core.db import SessionFactory
    from core.services import providers_admin

    # Admin kill-switch: a disabled image provider must not generate at all.
    async with SessionFactory() as s:
        if await providers_admin.is_disabled(s, model_key):
            raise RuntimeError(f"provider '{model_key}' disabled by admin")

    # 1) Resolve the ordered image accounts in a short session, then release it.
    # (account_id, gateway, upstream_model, cost_micros)  — FIX: AUDIT-G1
    resolved: list[tuple[int, object, str, int]] = []
    async with SessionFactory() as s:
        model = await routing.resolve_model(s, model_key)
        if model is not None and model.modality == "image":
            for acc in await routing.resolve_route(s, model):
                gw = routing.gateway_for_account(acc)
                if gw is not None and gw.is_available():
                    resolved.append((acc.id, gw, model.upstream_model, model.cost_micros or 0))

    # 2) Try each aggregator account with no session/connection held during HTTP.
    for account_id, gw, upstream, cost_micros in resolved:
        try:
            images = await gw.generate_image(upstream, prompt, cfg)
        except Exception as exc:  # noqa: BLE001 — mark health + try the next backend
            # FIX: F12 - _mark_failure wrapped so a DB hiccup doesn't abort the loop.
            try:
                async with SessionFactory() as s:
                    await _mark_failure(s, account_id, exc)
            except Exception:  # noqa: BLE001 — health-stat failure is non-fatal
                pass
            continue
        # FIX: F11 - mark_success wrapped so a health-stat failure doesn't discard
        # already-fetched images (which would cause the worker to refund a success).
        try:
            async with SessionFactory() as s:
                acc = await s.get(AIAccount, account_id)
                if acc is not None:
                    await routing.mark_success(s, acc, cost_micros=cost_micros)
        except Exception:  # noqa: BLE001 — health-stat failure is non-fatal
            pass
        return images

    # 3) Fall back to the direct env adapter (also runs without a session).
    return await direct_fn()
