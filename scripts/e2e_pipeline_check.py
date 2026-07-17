"""Self-contained end-to-end pipeline smoke test against the mock AI server.

Boots ``scripts.mock_ai_server`` on a free localhost port, then drives the REAL
generation code paths for every modality and asserts each completes:

    chat   -> registry.chat            -> mock /v1/chat/completions
    photo  -> process_photoeffect_job  -> managed/direct image -> mock
    video  -> process_video_job        -> Kie createTask/recordInfo -> mock
    music  -> process_music_job        -> Kie createTask/recordInfo -> mock
    search -> search_adapter.run_search -> ai_chat -> mock /v1/chat/completions
    stt    -> stt().transcribe          -> mock /v1/audio/transcriptions
    tts    -> tts().speak               -> mock /v1/audio/speech
    avatar -> process_avatar_job        -> Kie createTask/recordInfo -> mock

request -> GenerationJob -> worker -> provider(mock, real HTTP) -> job=complete
-> Telegram delivery (captured by a fake bot).

Exit code 0 = all flows passed, 1 = a flow failed, 2 = mock server never came up.
Intended as a CI job step (`python scripts/e2e_pipeline_check.py`) so a regression
anywhere in the generation pipeline fails the build — without needing real provider
keys or external services.

Stubbed boundaries (no real external services in CI): Telegram delivery
(``core.bot_client.get_bot``) and the external result rehost
(``storage.rehost_remote``). Everything else is production code. SQLite + fakeredis
stand in for Postgres + Redis (the same zero-infra doubles the unit suite uses).
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)  # runnable as `python scripts/e2e_pipeline_check.py`


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORT = _free_port()
MOCK = f"http://127.0.0.1:{PORT}"

# Env MUST be set before importing core.* (settings are cached at import).
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{tempfile.gettempdir()}/aibot_e2e_{os.getpid()}.db")
os.environ.setdefault("REDIS_URL", "memory://")
os.environ.setdefault("BOT_TOKEN", "123:test")
os.environ["OPENAI_BASE_URL"] = f"{MOCK}/v1"
os.environ["OPENAI_API_KEY"] = "mock-key"
os.environ["AI_BASE_URL_ALLOWLIST"] = "127.0.0.1,localhost"


def _start_mock() -> subprocess.Popen:
    env = {**os.environ, "PYTHONPATH": REPO_ROOT}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "scripts.mock_ai_server:app",
         "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "warning"],
        cwd=REPO_ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        if proc.poll() is not None:
            return proc  # died on startup
        try:
            with urllib.request.urlopen(f"{MOCK}/healthz", timeout=1) as r:
                if r.status == 200:
                    return proc
        except Exception:
            time.sleep(0.4)
    return proc


import asyncio  # noqa: E402 — after env setup


async def _run_flows() -> int:
    from core.db import SessionFactory, engine
    from core.models import Base, GenerationJob
    from core.models.ai_routing import AIAccount, AIModel
    from core.services.users import get_or_create_user

    UID = 4242
    sends: list[tuple[str, str]] = []

    class _FakeBot:
        async def send_photo(self, c, photo, **k): sends.append(("photo", str(photo)[:50]))
        async def send_video(self, c, video, **k): sends.append(("video", str(video)[:50]))
        async def send_audio(self, c, audio, **k): sends.append(("audio", str(audio)[:50]))
        async def send_document(self, c, d, **k): sends.append(("document", str(d)[:50]))
        async def send_message(self, c, t, **k): sends.append(("message", str(t)[:50]))
        async def send_media_group(self, c, media, **k): sends.append(("album", len(media)))
        async def download(self, fid): raise RuntimeError("no telegram in e2e")

    import core.bot_client as bc
    bc.get_bot = lambda: _FakeBot()
    from core.services import storage

    async def _passthrough(url, *a, **k):
        return url
    storage.rehost_remote = _passthrough

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with SessionFactory() as s:
        await get_or_create_user(s, UID)
        await s.commit()

    async def _seed(modality: str, model_key: str, upstream: str):
        async with SessionFactory() as s:
            s.add(AIModel(key=model_key, title=model_key.upper(),
                          upstream_model=upstream, modality=modality, account_kind=None))
            s.add(AIAccount(name=f"kie-{modality}", kind="kie", base_url=MOCK,
                            api_key="k", modality=modality, tier=0))
            await s.commit()

    async def _new_job(service, variant, pack, params):
        async with SessionFactory() as s:
            j = GenerationJob(user_id=UID, service=service, model_variant=variant,
                              params=params, cost_credits=1, pack_type=pack, status="pending")
            s.add(j)
            await s.commit()
            return j.job_id  # native UUID PK (SQLite bind needs the object, not str)

    async def _status(jid):
        async with SessionFactory() as s:
            j = await s.get(GenerationJob, jid)
            return (j.status, j.result_url) if j else (None, None)

    failures = 0

    # CHAT
    try:
        await _seed("text", "gpt", "mock-model")
        from core.ai_router.registry import chat
        res = await chat("gpt", "hello world", locale="en")
        txt = getattr(res, "text", None) or getattr(res, "content", str(res))
        ok = "mock" in str(txt).lower()
        print(f"{'PASS' if ok else 'FAIL'}  chat   -> {str(txt)[:60]!r}")
        failures += 0 if ok else 1
    except Exception as e:
        print(f"FAIL  chat   -> {type(e).__name__}: {e}")
        failures += 1

    # PHOTO / VIDEO / MUSIC (async workers)
    # (modality, model_key, upstream, service, pack, params, fn_name, module)
    media = [
        ("image", "nano_banana", "nano", "photo_effect", "image",
         {"prompt": "a cat", "count": 1, "ratio": "1:1"},
         "process_photoeffect_job", "workers.photoeffect_tasks"),
        ("video", "kling_ai", "kling-v1", "kling_ai", "video",
         {"prompt": "a dog runs", "duration": 5, "ratio": "16:9"},
         "process_video_job", "workers.video_tasks"),
        ("music", "suno", "suno-v4", "suno", "music",
         {"prompt": "lofi beat"},
         "process_music_job", "workers.music_tasks"),
    ]
    import importlib
    for modality, mkey, upstream, service, pack, params, fn_name, mod_name in media:
        try:
            await _seed(modality, mkey, upstream)
            jid = await _new_job(service, mkey, pack, params)
            fn = getattr(importlib.import_module(mod_name), fn_name)
            await fn({}, jid)
            st, url = await _status(jid)
            ok = st in ("complete", "delivered") and bool(url)
            print(f"{'PASS' if ok else 'FAIL'}  {modality:5} -> status={st} url={str(url)[:45]}")
            failures += 0 if ok else 1
        except Exception as e:
            print(f"FAIL  {modality:5} -> {type(e).__name__}: {e}")
            failures += 1

    # SEARCH (/s -> resolve_search_model -> ai_chat -> mock chat)
    try:
        async with SessionFactory() as s:
            s.add(AIModel(key="sonar", title="Sonar", upstream_model="sonar",
                          modality="text", account_kind=None, search=True, enabled=True))
            await s.commit()
        from core.ai_router.search_adapter import run_search
        from core.models import User
        async with SessionFactory() as s:
            u = await s.get(User, UID)
            res = await run_search(s, u, "latest AI news", "You are a search assistant.", "en")
        txt = getattr(res, "text", "")
        rok = getattr(res, "ok", False)
        ok = rok and "mock" in str(txt).lower()
        print(f"{'PASS' if ok else 'FAIL'}  search -> ok={rok} {str(txt)[:40]!r}")
        failures += 0 if ok else 1
    except Exception as e:
        print(f"FAIL  search -> {type(e).__name__}: {e}")
        failures += 1

    # STT (voice input -> mock /v1/audio/transcriptions)
    try:
        from core.ai_router.stt_adapter import stt
        text = await stt().transcribe(b"fake-ogg-audio", filename="voice.ogg", locale="en")
        ok = "mock" in text.lower()
        print(f"{'PASS' if ok else 'FAIL'}  stt    -> {text[:40]!r}")
        failures += 0 if ok else 1
    except Exception as e:
        print(f"FAIL  stt    -> {type(e).__name__}: {e}")
        failures += 1

    # TTS (voice output -> mock /v1/audio/speech)
    try:
        from core.ai_router.tts_adapter import tts
        audio = await tts().speak("hello world")
        ok = isinstance(audio, (bytes, bytearray)) and len(audio) > 0
        print(f"{'PASS' if ok else 'FAIL'}  tts    -> {len(audio) if audio else 0} bytes")
        failures += 0 if ok else 1
    except Exception as e:
        print(f"FAIL  tts    -> {type(e).__name__}: {e}")
        failures += 1

    # AVATAR (worker -> Kie image createTask/recordInfo -> mock -> album delivery)
    try:
        import workers.avatar_tasks as at

        # Stub the selfie-upload boundary (Telegram file download -> our storage),
        # which has no real bot/file here; the rest is production code.
        async def _fake_selfie(file_id, job_id):
            return "https://via.placeholder.com/selfie.jpg"
        at._upload_file_id = _fake_selfie

        await _seed("image", "avatar", "avatar-model")
        jid = await _new_job("avatar", "avatar", None,
                             {"prompt": "avatar", "selfie_file_id": "self123", "count": 1})
        await at.process_avatar_job({}, jid)
        st, url = await _status(jid)
        ok = st in ("complete", "delivered") and bool(url)
        print(f"{'PASS' if ok else 'FAIL'}  avatar -> status={st} url={str(url)[:45]}")
        failures += 0 if ok else 1
    except Exception as e:
        print(f"FAIL  avatar -> {type(e).__name__}: {e}")
        failures += 1

    print(f"deliveries captured: {sends}")
    await engine.dispose()
    try:
        os.remove(os.environ["DATABASE_URL"].split(":///")[1])
    except OSError:
        pass
    return failures


def main() -> int:
    proc = _start_mock()
    if proc.poll() is not None:
        print("ERROR: mock AI server failed to start", file=sys.stderr)
        return 2
    try:
        failures = asyncio.run(_run_flows())
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
    if failures:
        print(f"\nE2E FAILED: {failures} flow(s) did not complete")
        return 1
    print("\nE2E OK: all generation flows completed end-to-end")
    return 0


if __name__ == "__main__":
    sys.exit(main())
