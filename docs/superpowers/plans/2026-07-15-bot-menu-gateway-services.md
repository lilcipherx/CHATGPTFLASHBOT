# Bot Menu Gateway Services Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let any `/video` and `/photo` service work from the bot menu when a gateway account (or direct provider) is configured, instead of hard-blocking on the direct provider (video) or charge-then-refunding (photo).

**Architecture:** Add `media_dispatch.has_backend` (reuses `resolve_backends`) and use it as the pre-charge availability gate in `on_video_prompt` and `_run_photo`.

**Tech Stack:** Python 3.11+ async, SQLAlchemy 2 async, aiogram, pytest/pytest-asyncio.

## Global Constraints

- No charge when nothing can serve: the gate runs BEFORE any `packs.try_consume` / `consume_text`.
- Reuse `resolve_backends` (do not duplicate routing/kill-switch logic). `params={}` for the check (submit is never called).
- Workers unchanged. No schema/migration. Direct-provider services (Kling / GPT Image 2 / Nano Banana / FLUX with env keys) keep working.

---

### Task 1: `has_backend` helper

**Files:**
- Modify: `core/services/media_dispatch.py`
- Test: `tests/test_has_backend.py` (create)

**Interfaces:**
- Produces: `core.services.media_dispatch.has_backend(session, *, modality: str, model_key: str, direct_provider) -> bool`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_has_backend.py`:

```python
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_has_backend.py -v --no-cov -p no:cacheprovider`
Expected: FAIL (`has_backend` not defined).

- [ ] **Step 3: Add `has_backend` to `core/services/media_dispatch.py`**

Add after `resolve_backends`:

```python
async def has_backend(session, *, modality: str, model_key: str, direct_provider) -> bool:
    """True when a generation for (modality, model_key) has at least one usable backend
    — a configured gateway account (via the AIModel catalog) OR an available direct
    provider, and the provider key is not admin-disabled. Reuses resolve_backends so
    the pre-charge availability check matches what the worker will actually try."""
    backends = await resolve_backends(
        session, modality=modality, model_key=model_key, params={},
        direct_provider=direct_provider,
    )
    return bool(backends)
```

- [ ] **Step 4: Run to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_has_backend.py -v --no-cov -p no:cacheprovider`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add core/services/media_dispatch.py tests/test_has_backend.py
git commit -m "feat(media): add has_backend availability helper"
```

---

### Task 2: Gate /video + /photo on `has_backend`

**Files:**
- Modify: `bot/handlers/video.py` (`on_video_prompt`)
- Modify: `bot/handlers/photo.py` (`_run_photo`)

**Interfaces:**
- Consumes: `media_dispatch.has_backend` (Task 1); `bot.handlers.video.provider_for`; `core.ai_router.image_adapters._IMAGE_PROVIDERS`.

- [ ] **Step 1: Edit `bot/handlers/video.py`**

In `on_video_prompt`, replace this exact block:

```python
    provider = provider_for(service)
    if provider is None or not provider.is_available():
        await message.answer(_("gen.unavailable"))
        return
```

with:

```python
    from core.services.media_dispatch import has_backend
    if not await has_backend(session, modality="video", model_key=service,
                             direct_provider=provider_for(service)):
        await message.answer(_("gen.unavailable"))
        return
```

- [ ] **Step 2: Edit `bot/handlers/photo.py`**

In `_run_photo`, immediately after the docstring / before the `per = spec.cost(cfg)` line, insert:

```python
    from core.ai_router.image_adapters import _IMAGE_PROVIDERS
    from core.services.media_dispatch import has_backend
    if not await has_backend(session, modality="image", model_key=spec.key,
                             direct_provider=_IMAGE_PROVIDERS.get(spec.key)):
        await message.answer(_("gen.unavailable"))
        return
```

- [ ] **Step 3: Syntax-check both edited files**

Run: `./.venv/Scripts/python.exe -m py_compile bot/handlers/video.py bot/handlers/photo.py`
Expected: exit 0 (no output).

- [ ] **Step 4: Import-check (no circular import / typo)**

Run: `./.venv/Scripts/python.exe -c "import bot.handlers.video, bot.handlers.photo, core.services.media_dispatch as m; assert hasattr(m, 'has_backend')"`
Expected: exit 0.

- [ ] **Step 5: Full suite for regressions**

Run: `./.venv/Scripts/python.exe -m pytest tests/ --no-cov -p no:cacheprovider -q`
Expected: all pass (prior 1041 + Task 1's 3 new = 1044).

- [ ] **Step 6: Commit**

```bash
git add bot/handlers/video.py bot/handlers/photo.py
git commit -m "feat(bot): gate /video + /photo on has_backend so gateway services open"
```

---

## Self-Review

- **Spec coverage:** `has_backend` helper ✓; video gate replaced ✓; photo pre-charge gate ✓; no-charge when unavailable ✓; reuse resolve_backends (kill-switch honored) ✓; workers/schema unchanged ✓; back-compat direct providers ✓.
- **Placeholder scan:** none — full code + commands in every step.
- **Type consistency:** `has_backend(session, *, modality, model_key, direct_provider) -> bool` used identically in both handlers and the tests.

## Deploy (after both tasks pass)

PR `claude/bot-menu-gateway-services` → GitHub `main` → AWS via `scripts/atomic_release.sh
origin/main --expect-current 0044_missing_model_indexes --expect-head
0044_missing_model_indexes` (no migration).
