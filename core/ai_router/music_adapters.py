"""Music generation adapters — Suno V5.5 + Lyria 3 Pro (§8). Async submit/poll,
same shape as video. Gated on API key via is_available()."""
from __future__ import annotations

from core.ai_router.base import JobStatus, ProviderUnavailable
from core.config import settings


# FIX: AI-18 - Suno base URL is now configurable via settings.suno_base_url.
# The previous hardcoded `https://api.suno.ai/v1` is NOT a public endpoint —
# Suno's public API is at `https://api.suno.ai/v1` only for official partners.
# Most deployments use a Suno-compatible aggregator (e.g. self-hosted or
# third-party) with a different base URL. Default keeps the old value for
# back-compat; set SUNO_BASE_URL in .env to point at your aggregator.


class SunoMusic:
    name = "suno"

    @property
    def _BASE(self) -> str:
        # FIX: AI-18 - configurable base URL so deployments can point at a
        # Suno-compatible aggregator instead of the (non-public) api.suno.ai.
        return getattr(settings, "suno_base_url", "") or "https://api.suno.ai/v1"

    def is_available(self) -> bool:
        return bool(settings.suno_api_key)

    async def submit(self, params: dict) -> str:
        if not self.is_available():
            raise ProviderUnavailable(self.name)
        import httpx

        async with httpx.AsyncClient(timeout=60) as http:
            # FIX: H6 - official Suno API uses /music/generations (was /generate).
            # FIX: AI-18 - send `model` field so the UI-promised Suno version is
            # actually passed (was: only `prompt`, so Suno used its default model).
            body_payload = {
                "prompt": params.get("prompt", ""),
                "model": params.get("model") or "suno-v4",
            }
            r = await http.post(
                f"{self._BASE}/music/generations",
                headers={"Authorization": f"Bearer {settings.suno_api_key}"},
                json=body_payload,
            )
            r.raise_for_status()
            # FIX: AI-17 - list-safe parse. Suno's batch API returns an array
            # [{"id": ...}, ...], not a single object. The old `body.get("id")`
            # crashed with AttributeError on a list. Handle both shapes.
            body = r.json()
            tid = None
            if isinstance(body, list):
                # Batch response: take the first clip's id.
                if body and isinstance(body[0], dict):
                    tid = body[0].get("id")
            elif isinstance(body, dict):
                tid = body.get("id")
                if not tid:
                    # Some Suno variants nest under "data".
                    data = body.get("data") or []
                    if data and isinstance(data[0], dict):
                        tid = data[0].get("id")
            if not tid:
                raise ProviderUnavailable(self.name)
            return str(tid)

    async def poll(self, provider_job_id: str) -> JobStatus:
        import httpx

        async with httpx.AsyncClient(timeout=60) as http:
            # FIX: H6 - official Suno poll path is /music/generations/{id}.
            r = await http.get(
                f"{self._BASE}/music/generations/{provider_job_id}",
                headers={"Authorization": f"Bearer {settings.suno_api_key}"},
            )
            r.raise_for_status()
            # FIX: U6 - defensive: malformed Suno poll response -> processing, not crash.
            body = r.json() or {}
            data = body.get("data") or []
            # Suno v1 generation poll: status is on the body OR on each clip. Pick the
            # first clip's audio_url when complete; tolerate the legacy flat shape too.
            # FIX: AUDIT13-M1 - only report "complete" when the audio URL is actually
            # present. Previously a "complete" status with a missing/renamed audio_url
            # returned result_url=None, so the worker "delivered" nothing yet the user
            # was charged with no failure -> no refund (money leak). Mirror Kling, which
            # raises/stays-processing when the URL is absent.
            top_status = body.get("status")
            if not data and top_status == "complete":
                url = body.get("audio_url")
                return JobStatus("complete", result_url=url) if url else JobStatus("processing")
            if not data:
                if top_status == "error":
                    return JobStatus("failed", error="suno error")
                return JobStatus("processing")
            clip = data[0] if isinstance(data, list) else {}
            clip_status = clip.get("status") or top_status
            if clip_status == "complete":
                url = clip.get("audio_url")
                return JobStatus("complete", result_url=url) if url else JobStatus("processing")
            if clip_status == "error":
                return JobStatus("failed", error="suno error")
            return JobStatus("processing")


class LyriaMusic:
    """Google Lyria 3 Pro — gated on the Google API key.

    FIX: H8 - the Google Lyria API is NOT wired (submit/poll raise unconditionally).
    is_available() now returns False so the bot's /music menu hides Lyria instead of
    offering a service that always refunds ~30s later. Flip is_available() back to
    `bool(settings.google_api_key)` AND implement submit/poll when the real API lands.
    """

    name = "lyria"

    def is_available(self) -> bool:
        return False  # FIX: H8 - stub; never offer this service until it is really wired

    async def submit(self, params: dict) -> str:  # pragma: no cover - needs key
        raise ProviderUnavailable(self.name)

    async def poll(self, provider_job_id: str) -> JobStatus:  # pragma: no cover
        raise ProviderUnavailable(self.name)


_PROVIDERS = {"suno": SunoMusic(), "lyria": LyriaMusic()}


def provider_for(service_key: str):
    return _PROVIDERS.get(service_key)
