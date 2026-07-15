"""has_backend: True when resolve_backends yields any backend (gateway account or
available direct provider), else False."""
from __future__ import annotations

from core.services import media_dispatch as md


class _Prov:
    def __init__(self, avail):
        self._a = avail

    def is_available(self):
        return self._a


async def test_has_backend_true_when_backends(monkeypatch):
    async def _rb(*a, **k):
        return [object()]  # non-empty
    monkeypatch.setattr(md, "resolve_backends", _rb)
    assert await md.has_backend(None, modality="video", model_key="seedance",
                                direct_provider=_Prov(False)) is True


async def test_has_backend_false_when_empty(monkeypatch):
    async def _rb(*a, **k):
        return []
    monkeypatch.setattr(md, "resolve_backends", _rb)
    assert await md.has_backend(None, modality="video", model_key="seedance",
                                direct_provider=_Prov(False)) is False


async def test_has_backend_passes_args_through(monkeypatch):
    seen = {}

    async def _rb(session, *, modality, model_key, params, direct_provider):
        seen.update(modality=modality, model_key=model_key, params=params,
                    direct=direct_provider)
        return [1]
    monkeypatch.setattr(md, "resolve_backends", _rb)
    dp = _Prov(True)
    await md.has_backend("SESS", modality="image", model_key="midjourney", direct_provider=dp)
    assert seen == {"modality": "image", "model_key": "midjourney", "params": {}, "direct": dp}
