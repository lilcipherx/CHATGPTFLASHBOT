"""Media aggregator gateways — one adapter per multi-provider gateway.

A media gateway is an external service that exposes MANY image/video/music models
behind ONE key (Kie.ai, MuAPI, APIMart…). Unlike OmniRoute (text, OpenAI-chat
shaped), media gateways are task-based: submit → poll → result URL.

All gateways share the same async interface so the workers and the DB-driven
account router (core.services.ai_routing) treat them uniformly:

    submit(model, params) -> task_id
    poll(task_id)        -> JobStatus(status, result_url, error)
    generate_image(model, prompt, cfg) -> [ImageResult]   (submit+poll wrapper)

`build_gateway(kind, api_key, base_url)` constructs the right adapter from an
AIAccount row. Endpoint paths/auth below are taken from each gateway's public
docs; response *field* locations vary per model, so the parsers are defensive and
should be confirmed against a live key (see per-class notes).
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from core.ai_router.base import ImageResult, JobStatus, ProviderUnavailable


class MediaGateway:
    """Base task-based gateway. Subclasses implement submit() + poll()."""

    kind = "base"
    default_base_url = ""

    def __init__(self, api_key: str, base_url: str | None = None):
        self.api_key = api_key or ""
        self.base_url = (base_url or self.default_base_url).rstrip("/")

    def is_available(self) -> bool:
        return bool(self.api_key and self.base_url)

    async def submit(self, model: str, params: dict) -> str:  # pragma: no cover - abstract
        raise ProviderUnavailable(self.kind)

    async def poll(self, task_id: str) -> JobStatus:  # pragma: no cover - abstract
        raise ProviderUnavailable(self.kind)

    async def generate_image(
        self, model: str, prompt: str, cfg: dict, *, poll_interval: int = 2, max_polls: int = 60
    ) -> list[ImageResult]:
        """Synchronous-feel image generation on top of submit/poll (most media
        gateways generate images as async tasks too)."""
        if not self.is_available():
            raise ProviderUnavailable(self.kind)
        task_id = await self.submit(model, {"prompt": prompt, **(cfg or {})})
        for _ in range(max_polls):
            await asyncio.sleep(poll_interval)
            st = await self.poll(task_id)
            if st.status == "complete" and st.result_url:
                return [ImageResult(url=st.result_url)]
            if st.status == "failed":
                raise RuntimeError(st.error or f"{self.kind} image failed")
        raise RuntimeError(f"{self.kind} image timed out")


def _first_url(obj: Any) -> str | None:
    """Walk an arbitrary JSON result and return the first http(s) URL found.

    Media gateways nest the output URL differently per model (resultUrls[0],
    output.url, video_url, audio_url, data[0].url…); this finds it without us
    hard-coding every model's shape. Used only as a LAST resort by ``_result_url``
    after the known result fields are checked, so it can't shadow them."""
    if isinstance(obj, str):
        return obj if obj.startswith("http") else None
    if isinstance(obj, dict):
        for v in obj.values():
            url = _first_url(v)
            if url:
                return url
    if isinstance(obj, list):
        for v in obj:
            url = _first_url(v)
            if url:
                return url
    return None


# Keys that hold the actual generated media, in priority order. Checked BEFORE the
# generic walk so a preview/thumbnail/avatar URL the provider happens to place
# earlier in the JSON can't be returned instead of the real result.
_RESULT_KEYS = (
    "resultUrls", "result_urls", "resultUrl", "result_url",
    "videoUrl", "video_url", "audioUrl", "audio_url",
    "imageUrl", "image_url", "url", "output", "outputs", "result", "data",
)


def _result_url(obj: Any) -> str | None:
    """Extract the generated media URL, preferring known result fields over a
    generic scan. Falls back to ``_first_url`` only when no known field yields a
    URL, so an unusually-shaped response still resolves rather than failing."""
    if isinstance(obj, dict):
        for key in _RESULT_KEYS:
            if key in obj:
                url = _first_url(obj[key])
                if url:
                    return url
    return _first_url(obj)


def _result_urls(obj: Any) -> list[str]:
    """ALL http(s) URLs in the result, order-preserving + de-duplicated. Prefers the
    known result-key subtrees (so previews elsewhere don't intrude), else a full walk.
    Used for multi-image results (avatar)."""
    out: list[str] = []

    def _walk(o: Any) -> None:
        if isinstance(o, str):
            if o.startswith("http") and o not in out:
                out.append(o)
        elif isinstance(o, dict):
            for v in o.values():
                _walk(v)
        elif isinstance(o, list):
            for v in o:
                _walk(v)

    if isinstance(obj, dict):
        for key in _RESULT_KEYS:
            if key in obj:
                _walk(obj[key])
    if not out:
        _walk(obj)
    return out


class KieGateway(MediaGateway):
    """Kie.ai unified jobs API (image/video/music). Bearer auth, async tasks.

    Docs: POST /api/v1/jobs/createTask {model, input} -> data.taskId;
          GET  /api/v1/jobs/recordInfo?taskId= -> data.state + data.resultJson.
    """

    kind = "kie"
    default_base_url = "https://api.kie.ai"
    _DONE = {"success"}
    _FAIL = {"fail"}

    async def submit(self, model: str, params: dict) -> str:
        if not self.is_available():
            raise ProviderUnavailable(self.kind)
        import httpx

        async with httpx.AsyncClient(timeout=60) as http:
            r = await http.post(
                f"{self.base_url}/api/v1/jobs/createTask",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": model, "input": params or {}},
            )
            r.raise_for_status()
            # FIX: AUDIT13-L4 - tolerate a top-level array response (mirrors AI-17 for
            # Suno); .get() on a list would raise AttributeError after the user is charged.
            _body = r.json()
            data = (_body.get("data") if isinstance(_body, dict) else {}) or {}
        task_id = data.get("taskId") or data.get("task_id")
        if not task_id:
            raise RuntimeError("kie: no taskId in createTask response")
        return str(task_id)

    async def poll(self, task_id: str) -> JobStatus:
        import httpx

        async with httpx.AsyncClient(timeout=60) as http:
            r = await http.get(
                f"{self.base_url}/api/v1/jobs/recordInfo",
                headers={"Authorization": f"Bearer {self.api_key}"},
                params={"taskId": task_id},
            )
            r.raise_for_status()
            data = r.json().get("data") or {}
        return self._to_status(data)

    @classmethod
    def _to_status(cls, data: dict) -> JobStatus:
        state = (data.get("state") or "").lower()
        if state in cls._FAIL:
            return JobStatus("failed", error=data.get("failMsg") or "kie failed")
        if state in cls._DONE:
            raw = data.get("resultJson")
            parsed = raw
            if isinstance(raw, str) and raw:
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    parsed = raw
            url = _result_url(parsed)
            urls = _result_urls(parsed)
            if url:
                return JobStatus("complete", result_url=url, result_urls=urls)
            return JobStatus("failed", error="kie: no result url")
        return JobStatus("processing")


class MuapiGateway(MediaGateway):
    """MuAPI (muapi.ai) — x-api-key auth, async predictions.

    Docs: POST /api/v1/{model-slug} {prompt,...} -> request_id;
          GET  /api/v1/predictions/{request_id}/result -> status + output url.
    """

    kind = "muapi"
    default_base_url = "https://api.muapi.ai"
    _DONE = {"completed", "complete", "succeeded", "success"}
    _FAIL = {"failed", "error", "canceled", "cancelled"}

    async def submit(self, model: str, params: dict) -> str:
        if not self.is_available():
            raise ProviderUnavailable(self.kind)
        import httpx

        async with httpx.AsyncClient(timeout=60) as http:
            r = await http.post(
                f"{self.base_url}/api/v1/{model}",
                headers={"x-api-key": self.api_key},
                json=params or {},
            )
            r.raise_for_status()
            # FIX: AUDIT13-L4 - tolerate a top-level array response (mirrors AI-17).
            data = r.json()
            if not isinstance(data, dict):
                data = {}
        req_id = data.get("request_id") or data.get("id")
        if not req_id:
            raise RuntimeError("muapi: no request_id in submit response")
        return str(req_id)

    async def poll(self, task_id: str) -> JobStatus:
        import httpx

        async with httpx.AsyncClient(timeout=60) as http:
            r = await http.get(
                f"{self.base_url}/api/v1/predictions/{task_id}/result",
                headers={"x-api-key": self.api_key},
            )
            r.raise_for_status()
            data = r.json()
        return self._to_status(data)

    @classmethod
    def _to_status(cls, data: dict) -> JobStatus:
        status = (data.get("status") or "").lower()
        if status in cls._FAIL:
            return JobStatus("failed", error=data.get("error") or "muapi failed")
        if status in cls._DONE:
            payload = data.get("outputs") or data.get("output") or data.get("result") or data
            url = _result_url(payload)
            urls = _result_urls(payload)
            if url:
                return JobStatus("complete", result_url=url, result_urls=urls)
            return JobStatus("failed", error="muapi: no result url")
        return JobStatus("processing")


class ApimartGateway(MediaGateway):
    """APIMart — OpenAI-compatible gateway. Bearer auth.

    Images use the OpenAI Images schema (POST /v1/images/generations). Async
    video/music task endpoints are NOT in the OpenAI spec and must be confirmed
    against a live APIMart key before wiring, so submit/poll raise until then.

    FIX: AI-21 - added `supports_async_media = False` so media_dispatch.resolve_backends
    can pre-filter this gateway for video/music models instead of letting the user
    charge for a job that always refunds at submit time. Image generation still
    works (generate_image is fully wired).
    """

    kind = "apimart"
    default_base_url = "https://api.apimart.ai/v1"
    # FIX: AI-21 - flag this gateway as NOT supporting async video/music submit.
    # media_dispatch should skip it for video/music modality and only use it for
    # image generation (where generate_image is fully implemented).
    supports_async_media: bool = False

    _RATIO_TO_SIZE = {
        "1:1": "1024x1024", "16:9": "1536x1024", "9:16": "1024x1536",
        "4:3": "1536x1024", "3:4": "1024x1536",  # FIX: M16 - valid gpt-image-1 sizes
    }

    async def generate_image(
        self, model: str, prompt: str, cfg: dict, **_: object
    ) -> list[ImageResult]:
        if not self.is_available():
            raise ProviderUnavailable(self.kind)
        import httpx

        cfg = cfg or {}
        async with httpx.AsyncClient(timeout=120) as http:
            r = await http.post(
                f"{self.base_url}/images/generations",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": model,
                    "prompt": prompt,
                    "n": int(cfg.get("count", 1)),
                    "size": self._RATIO_TO_SIZE.get(cfg.get("ratio", "1:1"), "1024x1024"),
                },
            )
            r.raise_for_status()
            items = r.json().get("data") or []
        results = [ImageResult(url=it.get("url"), data=None) for it in items if it.get("url")]
        if not results:
            raise RuntimeError("apimart: no image url in response")
        return results

    async def submit(self, model: str, params: dict) -> str:
        # APIMart async media (video/music) endpoint not yet confirmed from docs.
        # FIX: AI-21 - this raise is correct, but callers should pre-filter via
        # `supports_async_media` so the user never reaches this point.
        raise ProviderUnavailable(f"{self.kind}: async media endpoint unconfirmed")


class OpenRouterMediaGateway(MediaGateway):
    """OpenRouter as a media gateway — one key for image AND video generation.

    Image: synchronous ``POST /api/v1/images`` {model, prompt} → data[].b64_json
    (base64). We decode it to bytes and hand back ImageResult(data=...), which the
    image workers upload to our storage exactly like any other result.

    Video: async ``POST /api/v1/videos`` {model, prompt, ...} → {id, polling_url,
    status}; poll ``GET /api/v1/videos/{id}`` → status + unsigned_urls. The
    unsigned_urls need our Bearer token to download, so on completion we fetch the
    content WITH auth and re-host it to our storage, returning a public result_url
    (the video worker's plain rehost_remote can't authenticate).

    NB: OpenRouter has NO music/song generation (only TTS), so this gateway is only
    used for image/video accounts — never music. Bind an AIAccount kind='openrouter'
    with modality='image' or 'video' in the admin panel to route through it.
    """

    kind = "openrouter"
    default_base_url = "https://openrouter.ai/api/v1"

    # OpenRouter's /images endpoint is OpenAI-Images shaped, so the bot's aspect
    # ratio maps to a concrete pixel size the same way ApimartGateway does. Without
    # this the user's 9:16 / 4:3 choice was silently dropped and every image came
    # back square (1024x1024).
    _RATIO_TO_SIZE = {
        "1:1": "1024x1024", "16:9": "1536x1024", "9:16": "1024x1536",
        "4:3": "1536x1024", "3:4": "1024x1536",
    }

    async def generate_image(
        self, model: str, prompt: str, cfg: dict, **_: object
    ) -> list[ImageResult]:
        if not self.is_available():
            raise ProviderUnavailable(self.kind)
        import base64

        import httpx

        # FIX: OPENROUTER-MEDIA - honour the requested count + aspect ratio instead of
        # dropping cfg. A count>1 request now asks OpenRouter for N images (was: always
        # 1, then partially refunded) and the size follows the user's ratio.
        cfg = cfg or {}
        body = {
            "model": model,
            "prompt": prompt,
            "n": max(1, int(cfg.get("count", 1) or 1)),
            "size": self._RATIO_TO_SIZE.get(cfg.get("ratio", "1:1"), "1024x1024"),
        }
        async with httpx.AsyncClient(timeout=180) as http:
            r = await http.post(
                f"{self.base_url}/images",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=body,
            )
            r.raise_for_status()
            body = r.json()
            data = (body.get("data") if isinstance(body, dict) else []) or []
        results: list[ImageResult] = []
        for it in data:
            if not isinstance(it, dict):
                continue
            b64 = it.get("b64_json")
            if b64:
                try:
                    results.append(ImageResult(data=base64.b64decode(b64)))
                except (ValueError, TypeError):
                    continue
            elif it.get("url"):
                results.append(ImageResult(url=it["url"]))
        if not results:
            raise RuntimeError("openrouter: no image in response")
        return results

    async def submit(self, model: str, params: dict) -> str:
        if not self.is_available():
            raise ProviderUnavailable(self.kind)
        import httpx

        params = params or {}
        body: dict = {"model": model, "prompt": params.get("prompt", "")}
        # Optional video knobs (OpenRouter names): map the bot's cfg keys across.
        ratio = params.get("aspect_ratio") or params.get("ratio")
        if ratio:
            body["aspectRatio"] = ratio
        if params.get("duration") is not None:
            body["duration"] = params["duration"]
        if params.get("resolution"):
            body["resolution"] = params["resolution"]
        async with httpx.AsyncClient(timeout=60) as http:
            r = await http.post(
                f"{self.base_url}/videos",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=body,
            )
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, dict):
                data = {}
        job_id = data.get("id")
        if not job_id:
            raise RuntimeError("openrouter: no video job id in submit response")
        return str(job_id)

    async def poll(self, task_id: str) -> JobStatus:
        import httpx

        async with httpx.AsyncClient(timeout=60) as http:
            r = await http.get(
                f"{self.base_url}/videos/{task_id}",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, dict):
                data = {}
        status = (data.get("status") or "").lower()
        if status == "failed":
            return JobStatus("failed", error=data.get("error") or "openrouter video failed")
        if status in ("completed", "complete"):
            urls = data.get("unsigned_urls") or []
            content_url = urls[0] if urls else None
            if not content_url:
                return JobStatus("failed", error="openrouter: no video url")
            # unsigned_urls require our Bearer to download → fetch + re-host so the
            # result is a public URL the video worker/Telegram can actually fetch.
            # FIX: OPENROUTER-MEDIA - retry a transient network/storage hiccup twice
            # before failing: the video is already generated (and billed upstream), so
            # a single blip on download/save must not discard it and refund the user.
            from core.services import storage

            last_exc: Exception | None = None
            for attempt in range(3):
                try:
                    async with httpx.AsyncClient(timeout=300) as http:
                        vr = await http.get(
                            content_url, headers={"Authorization": f"Bearer {self.api_key}"}
                        )
                        vr.raise_for_status()
                        video_bytes = vr.content
                    public = await storage.save_upload(video_bytes, "mp4", prefix="results")
                    return JobStatus("complete", result_url=public)
                except Exception as exc:  # noqa: BLE001 — surface as a job failure → refund
                    last_exc = exc
                    if attempt < 2:
                        await asyncio.sleep(2)
            return JobStatus("failed", error=f"openrouter: video fetch failed: {last_exc}")
        return JobStatus("processing")


# backend kind -> gateway class
MEDIA_GATEWAYS: dict[str, type[MediaGateway]] = {
    "kie": KieGateway,
    "muapi": MuapiGateway,
    "apimart": ApimartGateway,
    "openrouter": OpenRouterMediaGateway,
}


def build_gateway(kind: str, api_key: str, base_url: str | None = None) -> MediaGateway | None:
    """Construct the media gateway for an AIAccount kind, or None if the kind is
    not a media gateway. NB: 'openrouter' is BOTH a text account kind (handled by the
    OpenAI-compatible text path, which never calls this) AND — for image/video
    modality accounts — a media gateway here. media_dispatch only builds gateways for
    media-modality accounts, so a text openrouter account never reaches this."""
    cls = MEDIA_GATEWAYS.get(kind)
    return cls(api_key, base_url) if cls else None
