"""Provider SDK clients must carry an explicit, bounded request timeout.

Without it the OpenAI/Anthropic/Google SDKs default to a 600s (10-min) read
timeout, so a hung — not errored — upstream would block a live chat turn for ten
minutes AND defeat the router's fallback/retry (which advance only on a raised
error, never on a hang). Guards against a future adapter dropping the timeout.

Only the OpenAI SDK is installed in the dev/test venv (anthropic/google-genai are
lazy-imported behind their keys), so we assert the OpenAI-compatible clients — the
primary text path plus TTS/STT — which all share the same construction pattern.
"""
from __future__ import annotations

from core.ai_router.openai_adapter import (
    OpenAICompatibleText,
    deepseek_text,
    openai_text,
    openrouter_text,
)
from core.ai_router.stt_adapter import stt
from core.ai_router.tts_adapter import tts
from core.config import settings


def _read_timeout(client) -> float:
    """The httpx read timeout the SDK client will enforce per request."""
    t = client.timeout
    return float(getattr(t, "read", t))  # Timeout obj → .read; bare number → itself


def test_timeout_defaults_are_bounded():
    # A live chat turn must fail well before the SDK's 600s default.
    assert 0 < settings.ai_request_timeout <= 120
    assert 0 < settings.ai_image_timeout <= 300


def test_openai_compatible_client_carries_request_timeout():
    prov = OpenAICompatibleText("sk-test", base_url="https://api.openai.com/v1")
    assert _read_timeout(prov._get_client()) == settings.ai_request_timeout


def test_factory_text_providers_carry_timeout():
    # openai / deepseek / openrouter all build through OpenAICompatibleText, so the
    # single timeout fix covers every env-key text provider.
    for factory in (openai_text, deepseek_text, openrouter_text):
        prov = factory()
        prov._api_key = prov._api_key or "sk-test"  # force a client even with no key
        assert _read_timeout(prov._get_client()) == settings.ai_request_timeout


def test_tts_and_stt_clients_carry_timeout():
    t = tts()
    t._api_key = "sk-test"
    s = stt()
    s._api_key = "sk-test"
    assert _read_timeout(t._get_client()) == settings.ai_request_timeout
    assert _read_timeout(s._get_client()) == settings.ai_request_timeout
