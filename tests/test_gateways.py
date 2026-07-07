"""Media gateway adapters: registry, account→gateway builder, and the
status/result parsers (no network — only the pure response-classification logic)."""
from __future__ import annotations

from core.ai_router.gateways import (
    ApimartGateway,
    KieGateway,
    MuapiGateway,
    OpenRouterMediaGateway,
    _first_url,
    build_gateway,
)
from core.models.ai_routing import AIAccount
from core.services import ai_routing as routing
from core.services.crypto import encrypt


def test_build_gateway_registry():
    assert isinstance(build_gateway("kie", "k"), KieGateway)
    assert isinstance(build_gateway("muapi", "k"), MuapiGateway)
    assert isinstance(build_gateway("apimart", "k"), ApimartGateway)
    # OpenRouter is also a media gateway (image/video) — media_dispatch only builds it
    # for media-modality accounts, so a text openrouter account is unaffected.
    assert isinstance(build_gateway("openrouter", "k"), OpenRouterMediaGateway)
    # omniroute / unknown kinds are text-only, not media gateways
    assert build_gateway("omniroute", "k") is None


def test_gateway_defaults_and_availability():
    g = build_gateway("kie", "secret")
    assert g.base_url == "https://api.kie.ai"
    assert g.is_available() is True
    assert build_gateway("kie", "").is_available() is False
    # explicit base_url overrides the default and is stripped of trailing slash
    assert build_gateway("muapi", "k", "https://x/").base_url == "https://x"


def test_first_url_walks_nested_json():
    assert _first_url({"a": {"b": ["https://cdn/x.mp4"]}}) == "https://cdn/x.mp4"
    assert _first_url({"resultUrls": ["https://cdn/img.png"]}) == "https://cdn/img.png"
    assert _first_url({"status": "ok", "n": 3}) is None


def test_kie_status_parser():
    assert KieGateway._to_status({"state": "waiting"}).status == "processing"
    assert KieGateway._to_status({"state": "generating"}).status == "processing"
    fail = KieGateway._to_status({"state": "fail", "failMsg": "nope"})
    assert fail.status == "failed" and fail.error == "nope"
    ok = KieGateway._to_status(
        {"state": "success", "resultJson": '{"resultUrls": ["https://cdn/v.mp4"]}'}
    )
    assert ok.status == "complete" and ok.result_url == "https://cdn/v.mp4"
    # success with no parseable url → failed (don't silently mark complete)
    assert KieGateway._to_status({"state": "success", "resultJson": "{}"}).status == "failed"


def test_muapi_status_parser():
    assert MuapiGateway._to_status({"status": "processing"}).status == "processing"
    fail = MuapiGateway._to_status({"status": "failed", "error": "x"})
    assert fail.status == "failed" and fail.error == "x"
    ok = MuapiGateway._to_status({"status": "completed", "outputs": ["https://cdn/a.mp3"]})
    assert ok.status == "complete" and ok.result_url == "https://cdn/a.mp3"


async def test_gateway_for_account_decrypts_key():
    acc = AIAccount(name="kie1", kind="kie", base_url="https://api.kie.ai",
                    api_key=encrypt("sk-secret"), modality="video")
    g = routing.gateway_for_account(acc)
    assert isinstance(g, KieGateway)
    assert g.api_key == "sk-secret"   # decrypted from the stored ciphertext
    # a text-gateway account yields no media gateway
    acc.kind = "omniroute"
    assert routing.gateway_for_account(acc) is None
