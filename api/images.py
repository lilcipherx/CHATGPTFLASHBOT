"""Shared image helpers for upload endpoints — Mini App + admin banners/effects.

Content-based type detection (magic bytes, never the client filename), a Pillow
transcode-to-PNG normalization, and a structural validation. Lives in a neutral
module so the public router (``api.routers.miniapp``) and the admin routers
(``api.admin.banners`` / ``api.admin.effects``) don't import each other."""
from __future__ import annotations

import io

from fastapi import HTTPException
from PIL import Image


def _detect_image_ext(data: bytes) -> str | None:
    """Canonical extension from the file's MAGIC BYTES (not the client-supplied
    name), or None if it isn't one of the image types we accept."""
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def _normalize_image(data: bytes) -> tuple[bytes, str] | None:
    """Bytes + extension ready to store and serve.

    JPEG/PNG/WEBP pass through unchanged (cheap, lossless). Anything else that Pillow
    can decode — GIF, BMP, AVIF, TIFF, ICO… — is transcoded to PNG so the browser/Mini
    App always gets a renderable image instead of a broken one. Returns None when the
    bytes aren't a decodable image (e.g. HEIC without a HEIF plugin, or a non-image),
    so the caller can reject with a helpful message rather than storing a dead file."""
    ext = _detect_image_ext(data)
    if ext is not None:
        return data, ext
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.load()
            converted = im.convert("RGBA") if im.mode in ("RGBA", "LA", "P") else im.convert("RGB")
            out = io.BytesIO()
            converted.save(out, format="PNG")
            return out.getvalue(), ".png"
    except Exception:  # noqa: BLE001 — undecodable / unsupported → caller rejects
        return None


def _validate_image(data: bytes) -> str:
    """Return the canonical extension for an uploaded image, validating by CONTENT
    (magic bytes + a structural decode) rather than the client filename, so a
    non-image / corrupt / truncated file is rejected (415) before it reaches — and
    crashes — the generation worker."""
    ext = _detect_image_ext(data)
    if ext is None:
        raise HTTPException(status_code=415, detail="unsupported or non-image file")
    try:
        # verify() confirms the image is structurally intact without a full pixel
        # decode; it must be the first operation after open().
        Image.open(io.BytesIO(data)).verify()
    except Exception as exc:  # noqa: BLE001 — Pillow raises various types on bad data
        raise HTTPException(status_code=415, detail="corrupt or invalid image") from exc
    return ext
