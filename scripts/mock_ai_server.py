"""Local mock AI server — lets the whole stack run end-to-end with NO real keys.

It emulates the upstream APIs the bot/workers call, so you can develop and run
integration/load tests without spending money or owning provider accounts:

* OpenAI-compatible  POST /v1/chat/completions        (text router + OpenRouter)
* OpenAI-compatible  POST /v1/images/generations      (image adapters / APIMart)
* OpenAI Moderation  POST /v1/moderations             (core.services.moderation)
* Kie-style jobs     POST /api/v1/jobs/createTask      (media gateways: video/music)
                     GET  /api/v1/jobs/recordInfo
* MuAPI-style        POST /api/v1/{model}              + GET /api/v1/predictions/{id}/result

Run it:
    uvicorn scripts.mock_ai_server:app --port 8088

Point the app at it (.env):
    OPENAI_BASE_URL=http://localhost:8088/v1
    OPENAI_API_KEY=mock-key            # any non-empty value
And/or create AI accounts in the admin panel with base_url=http://localhost:8088
(add `localhost` to AI_BASE_URL_ALLOWLIST so the SSRF guard permits it).

Responses are deterministic and clearly fake — never use this in production.
"""
from __future__ import annotations

import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Mock AI Server", docs_url="/")

# A tiny static image (1x1 transparent PNG) served back as a result so image
# pipelines have a real, fetchable URL.
_PIXEL_URL = "https://via.placeholder.com/512.png"

_JOBS: dict[str, dict] = {}


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "service": "mock-ai"}


# ---- OpenAI-compatible text ------------------------------------------------
@app.post("/v1/chat/completions")
async def chat_completions(req: Request) -> dict:
    body = await req.json()
    model = body.get("model", "mock-model")
    messages = body.get("messages", [])
    last = messages[-1]["content"] if messages else ""
    reply = f"[mock:{model}] echo: {last}"[:2000]
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {"index": 0, "finish_reason": "stop",
             "message": {"role": "assistant", "content": reply}}
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
    }


# ---- OpenAI-compatible images ----------------------------------------------
@app.post("/v1/images/generations")
async def images_generations(req: Request) -> dict:
    body = await req.json()
    n = int(body.get("n", 1))
    return {"created": int(time.time()), "data": [{"url": _PIXEL_URL} for _ in range(n)]}


# ---- OpenAI Moderation -----------------------------------------------------
@app.post("/v1/moderations")
async def moderations(req: Request) -> dict:
    body = await req.json()
    text = str(body.get("input", "")).lower()
    # Flag only an obvious sentinel so tests can exercise both paths deterministically.
    flagged = "mock-flag-this" in text
    cats = {"sexual": False, "violence": flagged, "hate": False}
    return {
        "id": f"modr-{uuid.uuid4().hex[:12]}",
        "model": "omni-moderation-latest",
        "results": [{"flagged": flagged, "categories": cats,
                     "category_scores": {k: (0.99 if v else 0.0) for k, v in cats.items()}}],
    }


# ---- Kie-style async jobs (image/video/music) ------------------------------
@app.post("/api/v1/jobs/createTask")
async def kie_create(req: Request) -> dict:
    body = await req.json()
    task_id = uuid.uuid4().hex
    _JOBS[task_id] = {"created": time.time(), "model": body.get("model")}
    return {"code": 200, "data": {"taskId": task_id}}


@app.get("/api/v1/jobs/recordInfo")
async def kie_record(taskId: str = "") -> JSONResponse:  # noqa: N803 — upstream param name
    job = _JOBS.get(taskId)
    if job is None:
        return JSONResponse({"code": 404, "data": {}}, status_code=404)
    # Complete immediately (1s grace) so polling loops resolve fast in dev/tests.
    state = "success" if time.time() - job["created"] >= 0 else "processing"
    data = {"state": state}
    if state == "success":
        data["resultJson"] = {"resultUrls": [_PIXEL_URL]}
    return JSONResponse({"code": 200, "data": data})


# ---- MuAPI-style -----------------------------------------------------------
@app.post("/api/v1/predictions/{request_id}/result")
@app.get("/api/v1/predictions/{request_id}/result")
async def muapi_result(request_id: str) -> dict:
    return {"status": "completed", "outputs": [{"url": _PIXEL_URL}]}


@app.post("/api/v1/{model}")
async def muapi_submit(model: str) -> dict:
    return {"request_id": uuid.uuid4().hex, "model": model}
