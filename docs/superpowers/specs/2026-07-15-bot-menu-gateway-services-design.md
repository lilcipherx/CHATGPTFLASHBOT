# Bot /video + /photo — open all services via the gateway pool

**Date:** 2026-07-15
**Status:** approved (design)
**Scope:** `core/services/media_dispatch.py` (new `has_backend` helper) +
`bot/handlers/video.py` + `bot/handlers/photo.py`.

## Problem

The bot `/video` menu blocks every service whose DIRECT env-key provider is
unavailable: `on_video_prompt` gates on `provider_for(service).is_available()`, so the
stub video services (Veo, Seedance, Grok, Hailuo, Pika, MJ-video) show "unavailable"
even when an admin has configured a media-gateway account that COULD serve them via
the worker's `resolve_backends`. Only Kling (direct) works from the menu.

`/photo` already routes through the pool (`generate_image_routed_managed`), but it
charges FIRST and refunds if neither a gateway account nor the direct provider can
serve — a needless "charge then refund" cycle when the service is unconfigured.

## Goal

Let any service work from the bot menu when a gateway account (or direct provider) is
configured — matching the owner's plan to control every model via admin-added
gateways. Avoid charging when nothing can serve.

## Non-goals (YAGNI)

- Hiding unavailable services from the menu keyboards (out of scope; the pre-charge
  check is enough — the user just sees "unavailable" on submit).
- Any change to the workers (they already route via `resolve_backends`).
- Music `/music` (Suno direct + Lyria disabled) — unchanged.

## Design

### New helper — `core/services/media_dispatch.has_backend`
```python
async def has_backend(session, *, modality: str, model_key: str, direct_provider) -> bool:
    """True when a generation for (modality, model_key) has at least one usable
    backend: a configured gateway account (via the AIModel catalog) OR an available
    direct provider — and the provider key is not admin-disabled. Reuses
    resolve_backends so the availability check matches what the worker will actually
    try."""
    backends = await resolve_backends(
        session, modality=modality, model_key=model_key, params={}, direct_provider=direct_provider,
    )
    return bool(backends)
```
`resolve_backends` already: returns `[]` when the provider is admin-disabled; adds a
gateway backend per healthy account of the resolved `AIModel`; adds the direct
provider when available. `params={}` is safe — `submit` is never called here.

### `bot/handlers/video.py` — `on_video_prompt`
Replace:
```python
    provider = provider_for(service)
    if provider is None or not provider.is_available():
        await message.answer(_("gen.unavailable"))
        return
```
with:
```python
    from core.services.media_dispatch import has_backend
    if not await has_backend(session, modality="video", model_key=service,
                             direct_provider=provider_for(service)):
        await message.answer(_("gen.unavailable"))
        return
```
Everything after (charge video pack → create job → `enqueue_or_refund("process_video_job")`)
is unchanged; the worker's `resolve_backends` performs the real pool→direct routing.

### `bot/handlers/photo.py` — `_run_photo`
Add at the TOP of `_run_photo`, BEFORE any charge:
```python
    from core.ai_router.image_adapters import _IMAGE_PROVIDERS
    from core.services.media_dispatch import has_backend
    if not await has_backend(session, modality="image", model_key=spec.key,
                             direct_provider=_IMAGE_PROVIDERS.get(spec.key)):
        await message.answer(_("gen.unavailable"))
        return
```
This covers both the prompt path and the "🔄 ещё вариант" regenerate (both call
`_run_photo`). When configured, behaviour is unchanged (charge → pool → direct →
refund on real failure); when nothing can serve, the user is told immediately with no
charge/refund cycle.

## Admin configuration (no code; owner does this)
- Add `AIModel(key=<service key>, modality="video"|"image", upstream_model=<gateway slug>,
  account_kind=<optional pin>)` — service keys: video `seedance/veo/grok/kling_ai/
  hailuo/pika/mj_video`; photo `gpt_image2/nano_banana/seedream/midjourney/flux2/recraft`.
- Add `AIAccount(kind=<gateway>, modality=<video|image>, api_key, base_url, …)`.
- Then the service opens from the bot menu and routes through the pool.

## Backward compatibility
- Kling / GPT Image 2 / Nano Banana / FLUX with direct env keys → `has_backend` True
  (direct provider available) → unchanged.
- Nothing configured → `has_backend` False → "unavailable" (as before; photo also
  avoids the charge+refund cycle now).
- No handler flow change beyond the gate; no schema/migration.

## Testing (`tests/test_has_backend.py`)
- gateway account configured for the model → `has_backend` True (monkeypatch
  `resolve_backends` to return a non-empty list).
- direct provider available, no account → True.
- nothing available → False.
- (integration-style, optional) `resolve_backends` empty when admin-disabled → False.
Unit-level via monkeypatching `resolve_backends` keeps it fast and DB-free.

## Deploy
Local (pytest green) → GitHub `main` (PR) → AWS (`atomic_release.sh`, no migration).
