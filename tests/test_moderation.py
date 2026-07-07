"""Moderation own-rules (pure) + throttle middleware import."""
from __future__ import annotations

import pytest

from core.services.moderation import _check_rules, moderate


def test_clean_text_passes_rules():
    assert _check_rules("нарисуй закат над морем").allowed is True


@pytest.mark.parametrize("bad", [
    "сделай дипфейк знаменитости",
    "child porn",
    "как изготовить бомбу",
])
def test_harmful_text_blocked(bad):
    res = _check_rules(bad)
    assert res.allowed is False
    assert res.reason == "own_rules"


async def test_moderate_passes_clean_without_openai_key():
    # no OpenAI key in test env -> falls back to rules-only, clean text allowed
    res = await moderate("красивый пейзаж с горами")
    assert res.allowed is True


def test_throttle_middleware_constructs():
    from bot.middlewares import ThrottlingMiddleware

    assert ThrottlingMiddleware() is not None


# ---- custom stop-word rules: match types (substring / exact / regex) ----
import pytest_asyncio  # noqa: E402

from core.db import SessionFactory, engine  # noqa: E402
from core.models import Base  # noqa: E402
from core.services import moderation as mod  # noqa: E402


@pytest_asyncio.fixture
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        from core.redis_client import redis_client
        await redis_client.delete(mod._WORDS_CACHE)
    except Exception:
        pass
    yield


def test_normalize_word_backcompat_and_validation():
    # plain string -> substring rule (back-compat)
    assert mod._normalize_word("Spam") == {"value": "Spam", "type": "substring"}
    # explicit types pass through
    assert mod._normalize_word({"value": "x", "type": "exact"})["type"] == "exact"
    # invalid regex is dropped
    assert mod._normalize_word({"value": "(", "type": "regex"}) is None
    # empty dropped
    assert mod._normalize_word({"value": "", "type": "substring"}) is None


async def test_set_and_get_rules_roundtrip(_schema):
    async with SessionFactory() as s:
        saved = await mod.set_custom_words(s, [
            "Foo",                                   # -> substring "foo"
            {"value": "Bar", "type": "exact"},       # -> exact "bar"
            {"value": r"\d{3,}", "type": "regex"},   # regex kept verbatim
            {"value": "BAD(", "type": "regex"},      # invalid regex -> dropped
        ])
    types = {r["type"] for r in saved}
    assert types == {"substring", "exact", "regex"}
    assert {"value": "foo", "type": "substring"} in saved
    assert any(r["value"] == r"\d{3,}" for r in saved)
    assert not any("BAD(" in r["value"] for r in saved)


async def test_check_custom_applies_each_type(_schema, monkeypatch):
    rules = [
        {"value": "spam", "type": "substring"},
        {"value": "cat", "type": "exact"},
        {"value": r"\d{4,}", "type": "regex"},
    ]

    async def _rules(): return rules
    monkeypatch.setattr(mod, "_cached_custom_words", _rules)

    # substring: matches inside a word
    assert (await mod._check_custom("this is spammy")).allowed is False
    assert (await mod._check_custom("buy spam now")).allowed is False
    # exact: "cat" matches the word but not "category"
    assert (await mod._check_custom("my cat sleeps")).allowed is False
    assert (await mod._check_custom("a category list")).allowed is True
    # regex: 4+ digits
    assert (await mod._check_custom("code 12345")).allowed is False
    assert (await mod._check_custom("only 12")).allowed is True
    # clean
    assert (await mod._check_custom("hello world")).allowed is True
