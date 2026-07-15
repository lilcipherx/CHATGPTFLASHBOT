"""Provider-agnostic interfaces for the AI router (§7).

Handlers only ever talk to these dataclasses/protocols, so swapping a provider
never touches bot code. Every adapter implements `is_available()` and degrades
gracefully when its API key is missing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class Message:
    role: str  # system | user | assistant
    content: str


@dataclass
class TextResult:
    text: str
    model: str
    usage: dict = field(default_factory=dict)
    # False when `text` is a graceful fallback (provider unavailable / rate-limited)
    # rather than a real model answer — lets callers refund the consumed quota.
    ok: bool = True


@dataclass
class ImageResult:
    url: str | None = None
    data: bytes | None = None


@dataclass
class JobStatus:
    status: str  # pending | processing | complete | failed
    result_url: str | None = None
    error: str | None = None
    # Additive: ALL result URLs for multi-image jobs (avatar). Single-image callers
    # keep using result_url (== result_urls[0] when populated).
    result_urls: list[str] = field(default_factory=list)


class ProviderUnavailable(Exception):
    """Raised by an adapter that has no credentials / is killed-switched."""


@runtime_checkable
class TextProvider(Protocol):
    name: str

    def is_available(self) -> bool: ...

    async def chat(
        self, messages: list[Message], model: str, **opts
    ) -> TextResult: ...


@runtime_checkable
class ImageProvider(Protocol):
    name: str

    def is_available(self) -> bool: ...

    async def generate(
        self, prompt: str, *, count: int = 1, ratio: str = "1:1", **opts
    ) -> list[ImageResult]: ...


@runtime_checkable
class VideoProvider(Protocol):
    name: str

    def is_available(self) -> bool: ...

    async def submit(self, params: dict) -> str: ...  # -> provider_job_id

    async def poll(self, provider_job_id: str) -> JobStatus: ...
