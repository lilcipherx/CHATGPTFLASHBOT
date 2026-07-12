"""Video generation adapters — async submit/poll (§7).

Every video service is long-running, so adapters expose:
    submit(params) -> provider_job_id
    poll(provider_job_id) -> JobStatus(status, result_url, error)
The ARQ worker (workers/video_tasks.py) drives submit→poll→deliver. Adapters
gate on their API key via is_available(); exact endpoints/model ids are TODO
until keys arrive (Kling geo-limits, Veo waitlist — see §19)."""
from __future__ import annotations

from core.ai_router.base import JobStatus, ProviderUnavailable
from core.config import settings


class _BaseVideoProvider:
    name = "video"
    api_key_attr: str = ""
    # FIX: H7 - stub subclasses (those without their own submit/poll override) MUST
    # report unavailable, so the bot's "is this service ready?" check returns False
    # instead of letting a user charge for a job the worker will immediately refund.
    _is_stub: bool = False

    @property
    def _key(self) -> str:
        return getattr(settings, self.api_key_attr, "")

    def is_available(self) -> bool:
        # A stub provider is NEVER available, even if its env key is set — the
        # submit/poll bodies are not wired, so a "yes" here would let a user pay
        # for a generation that always refunds ~30s later (bad UX + wasted queue).
        if self._is_stub:
            return False
        return bool(self._key)

    async def submit(self, params: dict) -> str:
        raise ProviderUnavailable(self.name)

    async def poll(self, provider_job_id: str) -> JobStatus:
        raise ProviderUnavailable(self.name)


class KlingVideo(_BaseVideoProvider):
    name = "kling"
    api_key_attr = "kling_api_key"
    _BASE = "https://api.klingai.com/v1"

    def is_available(self) -> bool:
        # FIX: X4 - require BOTH access_key and secret_key (JWT needs both). Without
        # this, is_available() returns True with only the access key → user is charged →
        # _jwt() raises ProviderUnavailable → guaranteed refund cycle.
        return bool(self._key) and bool(getattr(settings, "kling_secret_key", ""))

    def _jwt(self) -> str:
        """FIX: H5 - Kling API requires a JWT (not a raw key). Generated from
        access_key (kling_api_key) + secret_key (kling_secret_key) via PyJWT."""
        import time

        import jwt  # PyJWT is in requirements.txt

        from core.config import settings

        access_key = self._key
        secret_key = getattr(settings, "kling_secret_key", "") or ""
        if not secret_key:
            raise ProviderUnavailable(self.name)
        now = int(time.time())
        payload = {"iss": access_key, "exp": now + 1800, "nbf": now - 5}
        return jwt.encode(payload, secret_key, algorithm="HS256", headers={"kid": access_key})

    async def submit(self, params: dict) -> str:
        if not self.is_available():
            raise ProviderUnavailable(self.name)
        import httpx

        # FIX: F5 - Kling requires a mode suffix: /text2video or /image2video.
        # FIX: M12 - transform image_ref → image_url so Kling receives the image.
        # FIX: F2 - check image_url (set by worker from image_file_id) for image2video.
        has_image = bool(params.get("image") or params.get("image_url") or params.get("image_ref"))
        endpoint = "image2video" if has_image else "text2video"
        # FIX: AUDIT-13 - operate on a copy, don't mutate caller's params dict
        params = {**params}
        if params.get("image_ref") and not params.get("image_url"):
            params["image_url"] = params.pop("image_ref")

        # FIX: AI-7 - build the REAL Kling API request body. The previous code sent
        # `params` verbatim, which contained spec-config keys like `model:"3.0"`,
        # `ratio`, `audio`, `fourk`, `image_file_id`, `template_id` — NONE of these
        # are real Kling API fields, so every Kling job 400'd and refunded.
        # Real Kling API fields (per https://docs.qingque.cn/):
        #   model: "kling-v1" | "kling-v2-master" (NOT "3.0"/"o1"/"2.6")
        #   prompt: str
        #   negative_prompt: str (optional)
        #   duration: "5" | "10" (STRING, not int)
        #   aspect_ratio: "16:9" | "9:16" | "1:1" (NOT "ratio")
        #   cfg_scale: float (0-1, default 0.5)
        #   callback_url: str (optional)
        #   external_task_id: str (optional)
        # For image2video: image: str (URL), image_tail: str (optional URL)
        spec_model = params.get("model") or "3.0"
        # FIX: AI-9 - map fictional spec model IDs to real Kling model IDs.
        kling_model = {
            "3.0": "kling-v1",
            "o1": "kling-v2-master",
            "2.6": "kling-v1",
            "2.5t": "kling-v1",
            "kling-v1": "kling-v1",
            "kling-v2-master": "kling-v2-master",
        }.get(spec_model, "kling-v1")

        spec_ratio = params.get("ratio") or params.get("aspect_ratio") or "16:9"
        # Kling accepts "16:9", "9:16", "1:1".
        if spec_ratio not in ("16:9", "9:16", "1:1"):
            spec_ratio = "16:9"

        spec_duration = params.get("duration")
        # Kling expects a STRING "5" or "10".
        if spec_duration is None:
            duration_str = "5"
        elif isinstance(spec_duration, (int, float)):
            duration_str = "5" if int(spec_duration) <= 5 else "10"
        else:
            duration_str = str(spec_duration)

        kling_body: dict = {
            # FIX: AUDIT-M12 - Kling's field is `model_name` (confirmed via official
            # docs), not `model`; the old key was ignored so Kling silently fell back
            # to its default model.
            "model_name": kling_model,
            "prompt": params.get("prompt") or "",
            "duration": duration_str,
            "aspect_ratio": spec_ratio,
        }
        if params.get("negative_prompt"):
            kling_body["negative_prompt"] = params["negative_prompt"]
        if params.get("cfg_scale") is not None:
            kling_body["cfg_scale"] = params["cfg_scale"]
        # image2video: Kling expects `image` (URL) — the worker already uploaded the
        # user's selfie to S3 and set params["image_url"]. Kling's field is `image`.
        if has_image:
            img_url = params.get("image_url") or params.get("image") or params.get("image_ref")
            if img_url:
                kling_body["image"] = img_url

        token = self._jwt()  # FIX: H5
        async with httpx.AsyncClient(timeout=60) as http:
            r = await http.post(
                # FIX: AUDIT-M12 - real Kling path is /v1/videos/{text2video|image2video};
                # there is no /generations/ segment (confirmed via official docs).
                f"{self._BASE}/videos/{endpoint}",
                headers={"Authorization": f"Bearer {token}"},
                json=kling_body,
            )
            r.raise_for_status()
            body = r.json() or {}
            tid = (body.get("data") or {}).get("task_id")
            if not tid:
                raise ProviderUnavailable(self.name)
            # FIX: AUDIT-M12 - Kling's query endpoint is PER-MODE
            # (GET /v1/videos/{mode}/{task_id}); poll() only receives the id, so carry
            # the mode back with it. The value is opaque to the workers (stored as
            # generation_jobs.provider_job_id and passed straight back to poll).
            return f"{endpoint}:{tid}"

    async def poll(self, provider_job_id: str) -> JobStatus:
        import httpx

        # FIX: AUDIT-M12 - split the mode carried by submit ("text2video:<id>"); fall
        # back to text2video for any legacy bare id from a job submitted pre-fix.
        mode, sep, task_id = provider_job_id.partition(":")
        if not sep:
            mode, task_id = "text2video", provider_job_id
        token = self._jwt()  # FIX: H5
        async with httpx.AsyncClient(timeout=60) as http:
            r = await http.get(
                f"{self._BASE}/videos/{mode}/{task_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            data = (r.json() or {}).get("data") or {}
            status = data.get("task_status")
            if status == "succeed":
                videos = ((data.get("task_result") or {}).get("videos")) or []
                if not videos:
                    raise ProviderUnavailable(self.name)
                url = videos[0].get("url")
                if not url:
                    raise ProviderUnavailable(self.name)
                return JobStatus("complete", result_url=url)
            if status == "failed":
                return JobStatus("failed", error=data.get("task_status_msg"))
            return JobStatus("processing")


# FIX: H7 - the six providers below have NO real submit/poll implementation (they
# inherit _BaseVideoProvider's `raise ProviderUnavailable`). Mark them as stubs so
# is_available() returns False and the bot's /video menu + Mini App hide them
# instead of offering a service that always refunds. Set _is_stub=False (and
# override submit/poll) on each when its real API is wired.
class GoogleVeo(_BaseVideoProvider):
    name = "veo"
    api_key_attr = "google_api_key"
    _is_stub = True


class SeedanceVideo(_BaseVideoProvider):
    name = "seedance"
    api_key_attr = "seedream_api_key"  # same vendor key family
    _is_stub = True


class HailuoVideo(_BaseVideoProvider):
    name = "hailuo"
    api_key_attr = "minimax_api_key"
    _is_stub = True


class GrokVideo(_BaseVideoProvider):
    name = "grok"
    api_key_attr = "xai_api_key"
    _is_stub = True


class PikaVideo(_BaseVideoProvider):
    name = "pika"
    api_key_attr = "pika_api_key"
    _is_stub = True


class MidjourneyVideo(_BaseVideoProvider):
    name = "mj_video"
    api_key_attr = "midjourney_api_key"
    _is_stub = True


# service_key -> provider instance. Kling powers AI/Effects/Motion (§20).
_PROVIDERS: dict[str, _BaseVideoProvider] = {
    "seedance": SeedanceVideo(),
    "veo": GoogleVeo(),
    "grok": GrokVideo(),
    "kling_ai": KlingVideo(),
    "hailuo": HailuoVideo(),
    "pika": PikaVideo(),
    "kling_effects": KlingVideo(),
    "kling_motion": KlingVideo(),
    "videoeffect": KlingVideo(),  # Mini App video effects (Kling-powered, §13.4)
    "mj_video": MidjourneyVideo(),
}


def provider_for(service_key: str) -> _BaseVideoProvider | None:
    return _PROVIDERS.get(service_key)
