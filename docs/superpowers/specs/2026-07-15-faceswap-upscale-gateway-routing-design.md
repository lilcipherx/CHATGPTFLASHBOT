# Face Swap + Upscale — gateway routing (remove stubs)

**Date:** 2026-07-15
**Status:** approved (design)
**Scope:** `workers/photo_tools_tasks.py` only. Avatar is a separate later spec.

## Problem

`process_faceswap_job` and `process_upscale_job` are stubs: they claim the job, then
immediately `_refund_and_fail(...)` + notify "unavailable". No provider is ever
called, so the tools can never deliver a result — adding a key/account in the admin
panel does NOT activate them, because the worker code has no provider call at all.

Money handling is already correct (the user is always refunded), but the features
are non-functional.

## Goal

Route Face Swap and Upscale through the SAME admin-configured gateway pool that the
video worker already uses (`core.services.media_dispatch`), so that:

- adding a media-gateway AI account in the admin panel activates the tool (no code
  change per provider);
- a NEW provider added later plugs in as just another account (future-proof);
- failover / cooldown / spend-limit / health tracking come for free from the pool.

## Non-goals (YAGNI)

- Avatar (separate spec: Stars refund semantics + ~100-image output + ~15 min).
- A per-model input-field mapping UI (see Caveat; start with a documented standard).
- Any change to the bot handlers (`bot/handlers/photo.py`) — they already charge +
  enqueue correctly; only the workers change.

## Design

Reuse the video worker's proven pattern (`workers/video_tasks.py`):
`resolve_backends` → `submit_or_resume` → poll loop → `rehost_remote` → deliver →
refund-on-failure. Face Swap / Upscale are image-modality submit/poll tasks.

### `process_faceswap_job(ctx, job_id)`
1. Load + atomically claim `pending → processing` (already implemented; keep).
2. Read input file_ids from `job.params` (`target`, `source`). If either missing →
   `_refund_and_fail`.
3. Download each from Telegram → `storage.save_upload(...)` → S3/MinIO URLs
   (mirrors `video_tasks` image upload). Best-effort with refund on failure.
4. Build `params = {"target_image": <url>, "source_image": <url>}` (documented
   standard input; see Caveat).
5. `backends = await resolve_backends(session, modality="image",
   model_key="faceswap", params=params, direct_provider=None)`.
   - `[]` (no account configured / admin kill-switch) → `_refund_and_fail` +
     `_notify_unavailable`. Preserves today's behaviour when unconfigured.
6. `submit_or_resume` (ARQ-retry safe: resume the owning backend, never re-submit) →
   persist `provider_job_id` + backend owner on the job (conditional UPDATE WHERE
   status='processing' AND refunded_at IS NULL, like `video_tasks`).
7. Poll loop outside the session (`POLL_INTERVAL`, `MAX_POLLS`): on `complete` +
   `result_url` → `rehost_remote` → deliver the image to chat → mark `complete`
   (conditional UPDATE). On `failed`/timeout → `_refund_and_fail` (re-check status
   first so a concurrent sweep can't double-refund).

### `process_upscale_job(ctx, job_id)`
Identical shape. Input: `job.params["image"]` (file_id) + `factor` (`x2`/`x4`).
`params = {"image": <url>, "scale": 2 | 4}`. `model_key="upscale"`.

### Delivery
Bot generations only (no Mini App origin for these tools yet), so chat is the sole
channel: claim `complete` first, then deliver; a send failure flips back to
`failed` + refund (mirrors `video_tasks._deliver_and_finalise` bot branch).

## Admin configuration (no code; owner does this)
- Add `AIModel(key="faceswap", modality="image", upstream_model=<gateway model slug>,
  account_kind=<optional pin>)` and the same for `"upscale"`.
- Add `AIAccount(kind=<gateway, e.g. kie>, modality="image", api_key=..., base_url=...,
  tier/priority/weight/spend_limit)`.
- Then the pool resolves and the tool works. Removing the account reverts to refund.

## Caveat (documented, expected)
Different gateways/models name face-swap / upscale input fields differently
(`source_image` vs `swap_image`, `scale` vs `upscale_factor`). This spec sends a
documented standard set (Kie unified-jobs convention). When a real model is wired,
the field names may need to match — a follow-up could add a small per-model param map
in the `ai_models` catalog. This is the same "confirm against a live key" posture the
existing gateways already carry.

## Backward compatibility
No account configured → `resolve_backends` returns `[]` → refund + "unavailable" =
exactly today's behaviour. No handler change, no migration, no schema change.

## Testing (mirror `test_video` / `test_worker_refunds`)
- success: submit accepted → poll complete → image delivered → job `complete`, no refund.
- no backend configured → job `failed` + refund + notify.
- submit fails on all backends → refund.
- provider poll `failed` / timeout → refund (once; sweep-safe).
- ARQ retry with existing `provider_job_id` → resumes poll, does NOT re-submit.
- delivery (send_photo) failure after claim → flip back to failed + refund.

## Deploy
Local (pytest green) → GitHub `main` (PR) → AWS (`atomic_release.sh`, no migration).
Feature flags `faceswap` / `upscale` stay admin-controlled (unchanged).
