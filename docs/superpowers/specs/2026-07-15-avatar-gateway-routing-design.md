# Avatar — gateway routing (remove stub)

**Date:** 2026-07-15
**Status:** approved (design)
**Scope:** `workers/avatar_tasks.py` + a small additive multi-URL extension to
`core/ai_router/base.py` (`JobStatus`) and `core/ai_router/gateways.py`.

## Problem

`process_avatar_job` is a stub: it claims the job, then `refund_stars(...)` +
fails, never calling a provider. Avatar never produces images — adding a key/account
in admin does nothing, because the worker has no provider call. (Money is safe: the
Stars purchase is always refunded.)

## Goal

Route Avatar through the same admin-configured media-gateway pool used by video and
by Face Swap / Upscale, so adding a gateway account activates it and new providers
plug in as accounts. Avatar produces MANY images (`params["count"]`, ~100), delivered
to chat as Telegram albums; on any genuine failure the Stars purchase is refunded.

## Non-goals (YAGNI)

- Saving avatars to the Mini App Gallery (possible later; adds a GalleryItem write per
  image).
- Two-phase train-then-generate provider flows (handled opaquely by the gateway
  submit/poll; not modelled here).
- Any change to the purchase / selfie-capture handlers in `bot/handlers/photo.py`.

## Design

### Multi-URL result (additive, back-compat)
- `core/ai_router/base.py`: add `result_urls: list[str] = field(default_factory=list)`
  to `JobStatus`. Existing `result_url` (single) is unchanged.
- `core/ai_router/gateways.py`: add `_result_urls(obj) -> list[str]` that collects
  ALL http(s) URLs from the result JSON (order-preserving, de-duplicated). In the
  `complete` branch of `KieGateway._to_status`, `MuapiGateway._to_status`, and
  `OpenRouterMediaGateway.poll`, populate `JobStatus(status="complete",
  result_url=urls[0], result_urls=urls)`. Single-image callers keep using
  `result_url` (== `urls[0]`), so video/faceswap/upscale behaviour is unchanged.

### `process_avatar_job(ctx, job_id)` (rewrite `workers/avatar_tasks.py`)
1. Load + atomically claim `pending → processing` (already implemented; keep). Read
   `charge_id`, `count`, `selfie_file_id` from `job.params`.
2. If no selfie → refund + fail.
3. Upload the selfie from Telegram → `storage.save_upload(...)` → URL (best-effort;
   failure → refund + fail).
4. `resolve_backends(session, modality="image", model_key="avatar",
   params={"image": <url>, "count": count}, direct_provider=None)`. `[]` (no account
   / admin kill-switch) → refund + fail + notify (preserves today's refund).
5. `submit_or_resume` (ARQ-retry safe) → persist `provider_job_id` + backend owner
   (conditional UPDATE WHERE status='processing' AND refunded_at IS NULL).
6. Poll loop outside the session (`POLL_INTERVAL`, `MAX_POLLS` sized for ~15-20 min):
   - `complete`: `urls = status.result_urls or ([status.result_url] if
     status.result_url else [])`. If empty → refund + fail. Else `rehost_remote`
     each (best-effort; keep provider URL on failure) → deliver as albums → mark
     `complete` (conditional UPDATE).
   - `failed` / timeout → refund + fail (re-check status first; sweep-safe).

### Delivery — `_deliver_albums(user_id, urls)`
Chunk `urls` into groups of 10 (Telegram media-group max) and send each as a
`send_media_group` of `InputMediaPhoto`, sleeping briefly between groups (rate
limit). Partial success is fine — deliver what arrived. Chat is the only channel;
if NOTHING could be delivered, refund + fail (parity with the video bot branch).

### Refund
Reuse `refund_job(session, job)` — it already routes `service == "avatar"` to
`refund_stars` (money-first, idempotent on the tx status, keyed by `charge_id`). So
the Stars-refund semantics are unchanged; only the "when" moves from "always" to
"on genuine failure".

## Admin configuration (no code; owner does this)
- Add `AIModel(key="avatar", modality="image", upstream_model=<gateway model slug>,
  account_kind=<optional pin>)`.
- Add `AIAccount(kind=<gateway>, modality="image", api_key=..., base_url=..., …)`.
- No account → refund Stars (today's behaviour).

## Caveat (documented, expected)
Avatar providers vary widely (image count, result shape, train+generate phases). The
multi-URL collector is a best-effort universal parse; a real model may need field
tuning — same posture as the other gateways.

## Backward compatibility
No account → `resolve_backends` returns `[]` → refund Stars + fail = today's
behaviour. `JobStatus.result_urls` is additive (default empty). No handler/schema/
migration change.

## Testing (`tests/test_avatar_gateway.py`)
- success (multi-URL): poll returns `result_urls=[u1,u2,...]` → `_deliver_albums`
  receives all URLs → job `complete`, no refund.
- success (single `result_url`, empty `result_urls`) → delivered as one-photo album.
- no backend configured → job `failed` + `refund_job` invoked (monkeypatched to
  record) + notify.
- provider `failed` / timeout → refund + fail.
- complete but zero URLs → refund + fail.
- ARQ retry with existing `provider_job_id` → resumes poll, does NOT re-submit.
- `JobStatus.result_urls` defaults to `[]` (base dataclass test).
- `gateways._result_urls` collects all http URLs, de-duped, order-preserving (unit).

## Deploy
Local (pytest green) → GitHub `main` (PR) → AWS (`atomic_release.sh`, no migration).
`avatar` feature flag stays admin-controlled (unchanged).
