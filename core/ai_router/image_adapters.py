"""Image generation adapters + a single `generate_image()` entrypoint.

Each provider gates on its API key via `is_available()` and raises
ProviderUnavailable otherwise, so the bot degrades gracefully (handler refunds
credits and shows "сервис временно недоступен"). Exact provider model ids /
endpoints are marked TODO where they need confirming once keys arrive (§7 risks).
"""
from __future__ import annotations

import os

from core.ai_router.base import ImageResult, ProviderUnavailable
from core.config import settings

_RATIO_TO_SIZE = {
    "1:1": "1024x1024",
    "16:9": "1536x1024",
    "9:16": "1024x1536",
    "4:3": "1536x1024",   # FIX: H4 - gpt-image-1 only accepts 1024x1024, 1024x1536, 1536x1024, auto
    "3:4": "1024x1536",   # FIX: H4
}

# Repo root, to resolve local "/media/..." upload refs in zero-infra dev.
_REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def _b64(value: str | None) -> bytes | None:
    """Decode a provider's base64 image payload to raw bytes (None if absent)."""
    if not value:
        return None
    import base64

    try:
        return base64.b64decode(value)
    except Exception:  # noqa: BLE001
        return None


async def _load_ref_bytes(ref: str) -> bytes | None:
    """Fetch the bytes of an uploaded image ref so a provider can do image-to-image.

    ``ref`` is what core.services.storage.save_upload returned: an http(s) URL
    (S3 / CDN / presigned) or a local ``/media/uploads/..`` path (dev fallback)."""
    if not ref:
        return None
    try:
        # FIX: AI-15 - use the ASYNC SSRF guard (_is_ssrf_url_async via asyncio.to_thread)
        # so DNS resolution doesn't block the event loop (was: sync _is_ssrf_url called
        # from this async function, blocking up to 5s per ref on slow DNS).
        if ref.startswith("https://"):
            from core.services.storage import _is_ssrf_url_async
            if await _is_ssrf_url_async(ref):
                return None
            import httpx

            async with httpx.AsyncClient(timeout=30) as http:
                r = await http.get(ref)
                r.raise_for_status()
                return r.content
        # FIX: H1 - path-traversal guard. `ref` is a /media/uploads/.. path that
        # came from a job row, which ultimately came from storage.save_upload() (a
        # trusted source) — BUT a normalised join on user-influenced input still
        # admits "../" escapes on misconfigured storages. Resolve to an absolute path
        # and verify it is still inside the allowed uploads root before reading.
        _UPLOADS_ROOT = os.path.realpath(os.path.join(_REPO_ROOT, "media", "uploads"))
        candidate = os.path.realpath(os.path.join(_REPO_ROOT, ref.lstrip("/")))
        if (candidate == _UPLOADS_ROOT or candidate.startswith(_UPLOADS_ROOT + os.sep)) \
                and os.path.isfile(candidate):
            with open(candidate, "rb") as fh:
                return fh.read()
    except Exception:  # noqa: BLE001 — a missing/unfetchable ref falls back to text2img
        return None
    return None


class OpenAIImage:
    name = "openai_image"

    def is_available(self) -> bool:
        return bool(settings.openai_api_key)

    async def generate(self, prompt: str, *, count: int, ratio: str, **opts) -> list[ImageResult]:
        if not self.is_available():
            raise ProviderUnavailable(self.name)
        from openai import AsyncOpenAI

        # Explicit base_url so the SDK never inherits an ambient OPENAI_BASE_URL;
        # explicit timeout so a stuck image call fails over instead of the SDK's 600s default.
        client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=settings.ai_image_timeout,
        )
        size = _RATIO_TO_SIZE.get(ratio, "1024x1024")

        # image-to-image: when the user uploaded photo(s), edit them with the prompt
        # (e.g. Mini App photo effects) instead of generating from text alone.
        import io

        refs = opts.get("image_refs") or []
        ref_blobs = [b for r in refs if (b := await _load_ref_bytes(r))]
        if ref_blobs:
            files = []
            for i, blob in enumerate(ref_blobs):
                buf = io.BytesIO(blob)
                buf.name = f"input_{i}.png"
                files.append(buf)
            resp = await client.images.edit(
                model=settings.openai_image_model,
                image=files if len(files) > 1 else files[0],
                prompt=prompt,
                n=count,
                size=size,
            )
            return [
                ImageResult(url=getattr(d, "url", None),
                            data=_b64(getattr(d, "b64_json", None)))
                for d in (resp.data or [])  # FIX: AUDIT13-L1 - guard None (TypeError otherwise)
            ]

        resp = await client.images.generate(
            model=settings.openai_image_model,
            prompt=prompt,
            n=count,
            size=size,
        )
        return [
            ImageResult(url=getattr(d, "url", None),
                        data=_b64(getattr(d, "b64_json", None)))
            for d in (resp.data or [])  # FIX: AUDIT13-L1 - guard None (TypeError otherwise)
        ]


class GoogleImage:
    """Nano Banana (Gemini Images)."""

    name = "google_image"

    def is_available(self) -> bool:
        return bool(settings.google_api_key)

    async def generate(self, prompt: str, *, count: int, ratio: str, **opts) -> list[ImageResult]:
        if not self.is_available():
            raise ProviderUnavailable(self.name)
        from google import genai
        from google.genai import types as genai_types

        # Explicit timeout (ms) so a stuck image call fails over instead of the SDK's
        # 600s default.
        client = genai.Client(
            api_key=settings.google_api_key,
            http_options={"timeout": settings.ai_image_timeout * 1000},
        )
        # FIX: F3+M11 - real google-genai image model IDs. NOTE: verify against a live
        # Google key which ID maps to Nano Banana Pro vs NB2 — the current mapping is a
        # best-effort guess based on Google's public model list. gemini-2.5-flash-image-preview
        # is the GA image model; gemini-2.0-flash-exp-image-generation is the older experimental.
        model = "gemini-2.5-flash-image-preview" if opts.get("model") == "nbpro" \
            else "gemini-2.0-flash-exp-image-generation"

        # image-to-image: when the user uploaded photo(s) (Mini App photo effects),
        # edit them with the prompt via generate_content (the photo + text become the
        # contents). Falls back to text-to-image when there are no usable refs.
        refs = opts.get("image_refs") or []
        ref_blobs = [b for r in refs if (b := await _load_ref_bytes(r))]
        if ref_blobs:
            parts: list = [prompt]
            for blob in ref_blobs:
                parts.append(genai_types.Part.from_bytes(data=blob, mime_type="image/png"))
            # FIX: H3 - Gemini image models require response_modalities to emit image
            # parts; without it the model returns text-only and out stays empty.
            resp = await client.aio.models.generate_content(
                model=model, contents=parts,
                config=genai_types.GenerateContentConfig(response_modalities=["Text", "Image"]),
            )
            out: list[ImageResult] = []
            for cand in getattr(resp, "candidates", []) or []:
                for part in getattr(cand.content, "parts", []) or []:
                    inline = getattr(part, "inline_data", None)
                    if inline and getattr(inline, "data", None):
                        out.append(ImageResult(data=inline.data))
            if out:
                return out
            raise RuntimeError("no image returned from img2img")

        # FIX: AI-4 - Google Nano Banana supports text-to-image too: send the prompt
        # as the sole content with response_modalities=["Image"]. The previous code
        # unconditionally raised ProviderUnavailable for text2img, which meant the
        # "Nano Banana Pro" service (advertised in PHOTO_SPECS as a prompt-only
        # service) was unreachable without an uploaded selfie. Now we attempt the
        # real text2img call; if Google rejects it (model variant doesn't support
        # text2img), the router falls back to the next provider via the raised
        # ProviderUnavailable below.
        try:
            resp = await client.aio.models.generate_content(
                model=model, contents=prompt,
                config=genai_types.GenerateContentConfig(response_modalities=["Image"]),
            )
            out: list[ImageResult] = []
            for cand in getattr(resp, "candidates", []) or []:
                for part in getattr(cand.content, "parts", []) or []:
                    inline = getattr(part, "inline_data", None)
                    if inline and getattr(inline, "data", None):
                        out.append(ImageResult(data=inline.data))
            if out:
                return out
        except Exception:  # noqa: BLE001 - model variant may not support text2img
            pass
        # Text2img not supported by this model variant → let the router fall back.
        raise ProviderUnavailable("google_image_text2img")


class BFLFlux:
    name = "bfl_flux"
    _BASE = "https://api.bfl.ml/v1"

    def is_available(self) -> bool:
        return bool(settings.bfl_api_key)

    async def generate(self, prompt: str, *, count: int, ratio: str, **opts) -> list[ImageResult]:
        if not self.is_available():
            raise ProviderUnavailable(self.name)
        import asyncio

        import httpx

        endpoint = {
            "flux2": "flux-2",
            "flux2_flex": "flux-2-flex",
            "flux2_pro": "flux-2-pro",
            "flux2_max": "flux-2-max",
        }.get(opts.get("model", "flux2"), "flux-2")
        headers = {"x-key": settings.bfl_api_key}
        # FIX: M10 - build body conditionally; don't send seed: null (BFL 422s on it).
        body = {"prompt": prompt, "aspect_ratio": ratio}
        if opts.get("seed") is not None:
            body["seed"] = opts.get("seed")

        # FIX: AI-6 - BFL img2img support. When the user uploaded photo(s), pass them
        # as `image` (for img2img endpoints) or as `image_prompt` reference. BFL's
        # FLUX 2 endpoint accepts `image` as a URL or base64-data URL for
        # image-to-image. We use the ref URL directly when it's https (BFL fetches it),
        # otherwise we encode the fetched bytes as a data URL.
        refs = opts.get("image_refs") or []
        if refs:
            import base64
            ref_url: str | None = None
            for r in refs:
                blob = await _load_ref_bytes(r)
                if blob:
                    # BFL accepts data:image/png;base64,<...> for image input.
                    ref_url = "data:image/png;base64," + base64.b64encode(blob).decode("ascii")
                    break  # BFL img2img takes 1 input image per call
            if ref_url:
                body["image"] = ref_url
                # img2img endpoints use the `-controlnet` or `-img2img` suffix on some
                # BFL variants; flux-2-flex-pro supports image input natively.
                if endpoint == "flux-2":
                    endpoint = "flux-2-flex"  # img2img variant

        # FIX: M9 - BFL generates 1 image per call; loop count times so the user
        # gets the count they paid for (was: count silently dropped, user pays N gets 1).
        results: list[ImageResult] = []
        async with httpx.AsyncClient(timeout=120) as http:
            for _img_idx in range(count):
                # FIX: #5 - wrap per-iteration body (POST+poll) in try/except so a
                # POST 429/5xx or network error doesn't discard accumulated partial
                # results (was: raise discarded everything → worker refunded full count
                # → backend paid for discarded images = money leak).
                try:
                    sub = await http.post(f"{self._BASE}/{endpoint}", headers=headers, json=body)
                    sub.raise_for_status()
                    b = sub.json() or {}
                    poll_url = b.get("polling_url")
                    if not poll_url:
                        raise ProviderUnavailable(self.name)
                    # FIX: AUDIT-13 - SSRF guard on BFL poll_url (provider-returned URL)
                    # FIX: AI-15 - use async SSRF guard to avoid blocking event loop.
                    from core.services.storage import _is_ssrf_url_async
                    if not poll_url.startswith("https://") or await _is_ssrf_url_async(poll_url):
                        raise ProviderUnavailable(self.name)
                    for attempt in range(60):
                        # FIX: AUDIT-172 - exponential backoff
                        await asyncio.sleep(2 * (1 + attempt // 10))
                        try:
                            res = (await http.get(poll_url, headers=headers)).json() or {}
                        except Exception as exc:
                            import structlog
                            structlog.get_logger().warning(
                                "bfl.poll_failed", attempt=attempt, error=str(exc))
                            continue
                        if res.get("status") == "Ready":
                            sample = (res.get("result") or {}).get("sample")
                            if sample:
                                results.append(ImageResult(url=sample))
                            break
                        # FIX: AUDIT-LOW - BFL also returns these TERMINAL statuses;
                        # treat them as failures immediately instead of polling all 60
                        # attempts (~2+ min) before giving up (esp. on moderated prompts).
                        if res.get("status") in {
                            "Error", "Failed", "Content Moderated",
                            "Request Moderated", "Task not found", "Task Not Found",
                        }:
                            raise RuntimeError(f"FLUX generation failed: {res.get('status')}")
                except Exception:
                    if results:
                        return results  # FIX: #5 - return partial results before re-raising
                    raise
        if not results:
            raise RuntimeError("FLUX generation produced no images")
        return results


class _UnavailableImage:
    """Placeholder for services without a real adapter yet. Reports unavailable so
    the handler refunds + shows "service unavailable" instead of silently
    substituting a different model (which would mislead the user)."""

    def __init__(self, name: str):
        self.name = name

    def is_available(self) -> bool:
        return False

    async def generate(self, prompt: str, **opts) -> list[ImageResult]:
        raise ProviderUnavailable(self.name)


# service_key -> provider. Only services with a genuine adapter are wired; the
# rest are honest placeholders until a real provider/model id is confirmed (§7),
# so we never present one model's output under another model's name.
_IMAGE_PROVIDERS = {
    "gpt_image2": OpenAIImage(),
    "nano_banana": GoogleImage(),
    "flux2": BFLFlux(),
    "seedream": _UnavailableImage("seedream"),
    "midjourney": _UnavailableImage("midjourney"),
    "recraft": _UnavailableImage("recraft"),
}


async def generate_image(service_key: str, prompt: str, config: dict) -> list[ImageResult]:
    provider = _IMAGE_PROVIDERS.get(service_key)
    if provider is None or not provider.is_available():
        raise ProviderUnavailable(service_key)
    return await provider.generate(
        prompt,
        count=int(config.get("count", 1)),
        ratio=config.get("ratio", "1:1"),
        model=config.get("model"),
        quality=config.get("quality"),
        seed=config.get("seed"),
        # /media URLs of the user's uploaded photo(s) for image-to-image. Adapters
        # accept **opts, so providers that support img2img can consume these; the
        # per-provider edit call is wired once real keys are available (§7).
        image_refs=config.get("image_refs") or [],
    )
