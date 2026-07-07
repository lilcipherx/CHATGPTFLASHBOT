"""Validate a media aggregator (Kie / MuAPI / APIMart) end-to-end with YOUR key.

Sets up nothing permanent — it hits the real endpoints, prints the RAW JSON of
every response, and shows what our adapter parser derives from it. Use this to
confirm the adapters against a live key and spot any field-name drift before
wiring the account in the admin panel.

    # set the key in your shell (never commit it), then:
    KIE_API_KEY=sk-...    python -m scripts.gateway_check kie    <model> "a cat surfing"
    MUAPI_API_KEY=...      python -m scripts.gateway_check muapi  <model-slug> "a cat surfing"
    APIMART_API_KEY=...    python -m scripts.gateway_check apimart <image-model> "a cat surfing"

<model> is the aggregator's own model id (e.g. a Kie video model, a MuAPI slug
like 'openai-sora-2-text-to-video', or an APIMart image model). For kie/muapi the
script submits a task then polls; for apimart it calls the (sync) images endpoint.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

import httpx

from core.ai_router.gateways import KieGateway, MuapiGateway

POLL_INTERVAL = 5
MAX_POLLS = 40

_ENV = {"kie": "KIE_API_KEY", "muapi": "MUAPI_API_KEY", "apimart": "APIMART_API_KEY"}


def _dump(label: str, data: object) -> None:
    print(f"\n--- {label} ---")
    print(json.dumps(data, indent=2, ensure_ascii=False)[:4000])


async def _check_kie(key: str, model: str, prompt: str) -> None:
    base = KieGateway.default_base_url
    headers = {"Authorization": f"Bearer {key}"}
    async with httpx.AsyncClient(timeout=60) as http:
        r = await http.post(f"{base}/api/v1/jobs/createTask", headers=headers,
                            json={"model": model, "input": {"prompt": prompt}})
        _dump(f"createTask HTTP {r.status_code}", r.json())
        r.raise_for_status()
        task_id = (r.json().get("data") or {}).get("taskId")
        if not task_id:
            raise SystemExit("no taskId — check the model id / input shape above")
        print(f"\ntaskId = {task_id}; polling…")
        for i in range(MAX_POLLS):
            await asyncio.sleep(POLL_INTERVAL)
            p = await http.get(f"{base}/api/v1/jobs/recordInfo", headers=headers,
                               params={"taskId": task_id})
            data = (p.json().get("data") or {})
            status = KieGateway._to_status(data)
            print(f"[{i}] state={data.get('state')!r} -> "
                  f"parsed={status.status} url={status.result_url}")
            if status.status in ("complete", "failed"):
                _dump("final recordInfo", p.json())
                return
    print("⏱ timed out")


async def _check_muapi(key: str, model: str, prompt: str) -> None:
    base = MuapiGateway.default_base_url
    headers = {"x-api-key": key}
    async with httpx.AsyncClient(timeout=60) as http:
        r = await http.post(f"{base}/api/v1/{model}", headers=headers, json={"prompt": prompt})
        _dump(f"submit HTTP {r.status_code}", r.json())
        r.raise_for_status()
        req_id = r.json().get("request_id") or r.json().get("id")
        if not req_id:
            raise SystemExit("no request_id — check the model slug / body shape above")
        print(f"\nrequest_id = {req_id}; polling…")
        for i in range(MAX_POLLS):
            await asyncio.sleep(POLL_INTERVAL)
            p = await http.get(f"{base}/api/v1/predictions/{req_id}/result", headers=headers)
            data = p.json()
            status = MuapiGateway._to_status(data)
            print(f"[{i}] status={data.get('status')!r} -> "
                  f"parsed={status.status} url={status.result_url}")
            if status.status in ("complete", "failed"):
                _dump("final result", data)
                return
    print("⏱ timed out")


async def _check_apimart(key: str, model: str, prompt: str) -> None:
    base = "https://api.apimart.ai/v1"
    async with httpx.AsyncClient(timeout=120) as http:
        r = await http.post(f"{base}/images/generations",
                            headers={"Authorization": f"Bearer {key}"},
                            json={"model": model, "prompt": prompt, "n": 1, "size": "1024x1024"})
        _dump(f"images/generations HTTP {r.status_code}", r.json())
        r.raise_for_status()


_CHECKS = {"kie": _check_kie, "muapi": _check_muapi, "apimart": _check_apimart}


def main() -> None:
    if len(sys.argv) < 3 or sys.argv[1] not in _CHECKS:
        raise SystemExit(
            "usage: python -m scripts.gateway_check <kie|muapi|apimart> <model> [prompt]"
        )
    kind, model = sys.argv[1], sys.argv[2]
    prompt = sys.argv[3] if len(sys.argv) > 3 else "a red fox in the snow, cinematic"
    key = os.environ.get(_ENV[kind], "")
    if not key:
        raise SystemExit(f"❌ set {_ENV[kind]} in your environment first")
    asyncio.run(_CHECKS[kind](key, model, prompt))


if __name__ == "__main__":
    main()
