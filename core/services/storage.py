"""Object storage for user uploads (S3 / MinIO) with a local-disk fallback.

Why this exists (H-2): the Mini App used to persist uploaded photos on the API
container's local disk and hand back a ``/media/...`` path. That breaks the moment
the API runs on more than one replica/host — the worker (a different container)
and other API replicas can't see a file written to one replica's disk, so img2img
fails and ``/media`` 404s.

Behaviour:
* When S3 is configured (``S3_ENDPOINT`` + keys, e.g. the bundled MinIO), uploads
  go to the bucket and we return a URL any container / external AI provider can
  fetch — a public CDN URL if ``S3_PUBLIC_URL`` is set, otherwise a presigned GET
  URL (valid up to 7 days, enough for the worker to run img2img).
* When S3 is NOT configured (zero-infra dev / tests), we fall back to the old
  local-disk behaviour so nothing extra is needed to run locally.
"""
from __future__ import annotations

import os
import uuid
from urllib.parse import urlparse

from core.config import settings

# Presigned GET lifetime. SigV4 caps this at 7 days; a queued generation runs well
# within that, and the input photo is disposable afterwards.
_PRESIGN_TTL = 7 * 24 * 3600

_CONTENT_TYPE = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

# Local fallback dir (mirrors the previous api.routers.miniapp behaviour). Served
# by api.main's StaticFiles mount at /media.
_MEDIA_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "media")


def s3_enabled() -> bool:
    """True when an object store is configured (prod / MinIO)."""
    return bool(settings.s3_endpoint and settings.s3_key and settings.s3_secret)


def _content_type(ext: str) -> str:
    return _CONTENT_TYPE.get(ext.lower(), "application/octet-stream")


def _local_put(key: str, data: bytes) -> str:
    """Persist to local disk (dev fallback) and return the /media URL."""
    path = os.path.join(_MEDIA_ROOT, key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    return f"/media/{key}"


def _s3_client_ctx():
    """aioboto3 S3 client bound to the configured endpoint (MinIO/S3)."""
    import aioboto3

    session = aioboto3.Session()
    return session.client(
        "s3",
        endpoint_url=settings.s3_endpoint or None,
        aws_access_key_id=settings.s3_key,
        aws_secret_access_key=settings.s3_secret,
        region_name="us-east-1",  # arbitrary; MinIO ignores it, AWS needs one
    )


async def _ensure_bucket(s3) -> None:
    from botocore.exceptions import ClientError

    try:
        await s3.head_bucket(Bucket=settings.s3_bucket)
    except ClientError:
        try:
            await s3.create_bucket(Bucket=settings.s3_bucket)
        except ClientError as exc:
            import structlog
            structlog.get_logger().warning('core.services.storage._ensure_bucket_failed', error=str(exc))
            # FIX: AUDIT12-L1 - was silent except: pass (# already exists / created concurrently — put_object will surface real errors)


async def _s3_put(key: str, data: bytes, ext: str) -> str:
    async with _s3_client_ctx() as s3:
        await _ensure_bucket(s3)
        await s3.put_object(
            Bucket=settings.s3_bucket,
            Key=key,
            Body=data,
            ContentType=_content_type(ext),
        )
        if settings.s3_public_url:
            return f"{settings.s3_public_url.rstrip('/')}/{key}"
        return await s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_bucket, "Key": key},
            ExpiresIn=_PRESIGN_TTL,
        )


def is_owned_url(url: str) -> bool:
    """True if ``url`` already points at OUR storage — a local ``/media/...`` file or
    an object under the configured ``S3_PUBLIC_URL``. Used to skip a redundant re-host
    of a result we just saved ourselves (e.g. the OpenRouter gateway auth-downloads and
    re-hosts its video before returning it)."""
    if not url:
        return False
    if url.startswith("/media/"):
        return True
    pub = (settings.s3_public_url or "").rstrip("/")
    return bool(pub and url.startswith(pub + "/"))


async def delete(url: str) -> bool:
    """Best-effort delete of one of OUR stored objects, by its URL. Local `/media/...`
    files and S3 objects served under ``S3_PUBLIC_URL`` are removed; provider URLs and
    presigned URLs (which we can't safely map to a key) are left untouched (returns
    False). Never raises — used by the retention sweep, which must not fail on storage."""
    if not url:
        return False
    try:
        if url.startswith("/media/"):
            # FIX: H2 - path-traversal guard. Resolve to an absolute path and verify
            # it is still inside _MEDIA_ROOT before unlinking — a crafted "/media/.."
            # URL would otherwise let a caller delete arbitrary files on disk.
            _media_root_real = os.path.realpath(_MEDIA_ROOT)
            path = os.path.realpath(os.path.join(_MEDIA_ROOT, url[len("/media/"):]))
            if (path == _media_root_real or path.startswith(_media_root_real + os.sep)) \
                    and os.path.isfile(path):
                os.remove(path)
                return True
            return False
        pub = (settings.s3_public_url or "").rstrip("/")
        if pub and url.startswith(pub + "/"):
            key = url[len(pub) + 1:]
            async with _s3_client_ctx() as s3:
                await s3.delete_object(Bucket=settings.s3_bucket, Key=key)
            return True
        return False  # presigned / external provider URL — not ours, don't touch
    except Exception:  # noqa: BLE001 — storage cleanup is best-effort
        return False


async def save_upload(data: bytes, ext: str, *, prefix: str = "uploads") -> str:
    """Persist an uploaded file and return a URL that the worker and external AI
    providers can fetch. Uses S3/MinIO when configured, else local disk.

    ``ext`` is the (already validated) file extension including the leading dot.
    """
    if not ext.startswith("."):
        ext = f".{ext}" if ext else ""
    key = f"{prefix}/{uuid.uuid4().hex}{ext}"
    if s3_enabled():
        return await _s3_put(key, data, ext)
    return _local_put(key, data)


# Result re-hosting (ТЗ §13): a provider result URL can expire / be unreachable by
# Telegram, breaking History + Download later. We copy the finished result into OUR
# storage and serve our own URL instead. Best-effort: any failure returns None so the
# caller keeps the provider URL — re-hosting must NEVER break an already-paid result.
_REHOST_MAX_BYTES = 80 * 1024 * 1024   # 80 MB ceiling (videos can be large)
_RESULT_EXT_BY_CT = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
    "video/mp4": ".mp4", "video/webm": ".webm", "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a", "audio/wav": ".wav",
}
_RESULT_EXT_OK = set(_RESULT_EXT_BY_CT.values())


def _result_ext(url: str, content_type: str | None) -> str:
    """Pick a file extension from the content-type, falling back to the URL suffix."""
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct in _RESULT_EXT_BY_CT:
        return _RESULT_EXT_BY_CT[ct]
    ext = os.path.splitext(urlparse(url).path)[1].lower()
    return ext if ext in _RESULT_EXT_OK else ".bin"


def _is_ssrf_url(url: str) -> bool:
    """FIX: H3 - SSRF guard. True if the URL's resolved host is a private/loopback/
    link-local/reserved address — the classic SSRF targets (cloud metadata endpoint
    at 169.254.169.254, internal services on 10.x/192.168.x, localhost). Used by
    rehost_remote so a malicious provider result URL can't turn the worker into a
    proxy that fetches (and stores) internal-only responses.

    NOTE: this is the SYNC variant retained for callers that already run in a
    thread pool. Async callers should use ``_is_ssrf_url_async`` so DNS resolution
    runs in a worker thread and doesn't block the event loop (FIX: AUDIT12-M4)."""
    import ipaddress
    from urllib.parse import urlparse

    try:
        host = (urlparse(url).hostname or "").lower()
        if not host:
            return True  # no host -> treat as unsafe
        # Literal IP first.
        try:
            ips = [ipaddress.ip_address(host)]
        except ValueError:
            ips = _resolve_ssrf_candidates(host)
        for ip in ips:
            if ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_reserved:
                return True
        return False
    except Exception:  # noqa: BLE001 — fail-closed: ambiguous -> unsafe
        return True


def _resolve_ssrf_candidates(host: str) -> list:
    """Sync DNS resolver for ``_is_ssrf_url`` (and its async twin). Returns the list
    of IP addresses the host resolves to; an empty list on DNS failure (the
    caller treats empty as 'no private IP found' → safe, matching the original
    fail-open semantics for unresolvable provider URLs). Extracted as a helper so
    the async variant can run it in ``asyncio.to_thread`` (FIX: AUDIT12-M4)."""
    import ipaddress
    import socket

    socket.setdefaulttimeout(5)
    ips: list = []
    try:
        for info in socket.getaddrinfo(host, None):
            try:
                ips.append(ipaddress.ip_address(info[4][0]))
            except ValueError:
                continue
    except OSError:
        # Unresolvable: leave ips empty. The caller's `for ip in ips:` loop is a
        # no-op and the function returns False (safe). This matches the original
        # behaviour where a bad DNS response did not mark the URL as SSRF.
        return ips
    return ips


async def _is_ssrf_url_async(url: str) -> bool:
    """Async variant of ``_is_ssrf_url`` — same SSRF checks, but DNS resolution
    runs in a worker thread via ``asyncio.to_thread`` so the event loop is not
    blocked on a slow/unresponsive resolver (FIX: AUDIT12-M4).

    Used by ``rehost_remote`` and the image-adapter SSRF guards so a slow DNS
    response can't stall the worker pool. The sync ``_is_ssrf_url`` is kept for
    any caller that already runs in a thread pool."""
    import asyncio
    import ipaddress
    from urllib.parse import urlparse

    try:
        host = (urlparse(url).hostname or "").lower()
        if not host:
            return True  # no host -> treat as unsafe
        # Literal IP first.
        try:
            ips = [ipaddress.ip_address(host)]
        except ValueError:
            # FIX: AUDIT12-M4 - run the blocking DNS lookup in a thread pool to
            # avoid stalling the event loop on a slow resolver.
            ips = await asyncio.to_thread(_resolve_ssrf_candidates, host)
        for ip in ips:
            if ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_reserved:
                return True
        return False
    except Exception:  # noqa: BLE001 — fail-closed: ambiguous -> unsafe
        return True


async def rehost_remote(
    url: str, *, prefix: str = "results", max_bytes: int = _REHOST_MAX_BYTES,
) -> str | None:
    """Download a finished result from ``url`` and store it in our storage, returning
    OUR URL — or None on ANY failure (too big, network, decode, SSRF), so the caller
    falls back to the original provider URL. Never raises."""
    if not url or not url.lower().startswith(("http://", "https://")):
        return None
    # FIX: OPENROUTER-MEDIA - idempotent re-host. A result already in OUR storage
    # (the OpenRouter gateway auth-downloads + re-hosts its video itself, returning our
    # S3_PUBLIC_URL) must not be downloaded and re-uploaded a second time — return it
    # unchanged so the worker keeps the existing URL without duplicating the object.
    if is_owned_url(url):
        return url
    # FIX: H3 - reject SSRF targets BEFORE the worker fetches them. A provider that
    # returns http://169.254.169.254/... would otherwise have us download the cloud
    # metadata response and re-host it inside our own storage.
    # FIX: AUDIT12-M4 - use the async SSRF guard so DNS resolution runs in a thread
    # pool and doesn't block the event loop.
    if await _is_ssrf_url_async(url):
        return None
    try:
        import httpx

        # FIX: AUDIT13-M23 - follow redirects MANUALLY with follow_redirects=False so we
        # SSRF-validate EVERY hop BEFORE httpx connects to it. With follow_redirects=True
        # httpx fetches each intermediate hop itself (e.g. a 302 -> 169.254.169.254) and
        # only the FINAL url was re-checked, so an internal-only intermediate was still
        # contacted. Re-validating each Location closes that gap (and shrinks the DNS-
        # rebinding window to a single guarded resolve per hop).
        next_url = url
        async with httpx.AsyncClient(timeout=180, follow_redirects=False) as http:
            for _hop in range(5):
                # FIX: AUDIT-P6 - STREAM the body instead of buffering resp.content up
                # front. A hostile/compromised provider (or a redirect we followed) could
                # return a multi-GB body; `resp = await http.get(...)` used to read ALL of
                # it into RAM *before* the `len(data) > max_bytes` check, so the size cap
                # could not prevent an OOM. Now we (a) reject early on a declared
                # Content-Length and (b) stop reading the instant the running total passes
                # the cap, so at most one chunk beyond max_bytes is ever held.
                async with http.stream("GET", next_url) as resp:
                    if getattr(resp, "is_redirect", False):
                        loc = resp.headers.get("location")
                        if not loc:
                            return None
                        next_url = str(resp.url.join(loc))
                        # Validate the redirect TARGET before the next request touches it.
                        if not next_url.lower().startswith(("http://", "https://")) or \
                                await _is_ssrf_url_async(next_url):
                            return None
                        continue
                    resp.raise_for_status()
                    # Cheap pre-check: a truthful Content-Length lets us bail before
                    # reading a single byte of an oversize response.
                    clen = resp.headers.get("content-length")
                    if clen is not None:
                        try:
                            if int(clen) > max_bytes:
                                return None
                        except (TypeError, ValueError):
                            pass
                    ct = resp.headers.get("content-type")
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in resp.aiter_bytes():
                        total += len(chunk)
                        if total > max_bytes:
                            return None  # over the cap — abort without reading the rest
                        chunks.append(chunk)
                    data = b"".join(chunks)
                    if not data:
                        return None
                    return await save_upload(data, _result_ext(url, ct), prefix=prefix)
            else:
                return None  # too many redirects
    except Exception:  # noqa: BLE001 — re-hosting is best-effort; keep the provider URL
        return None
