"""Internet-search (/s) routing: premium gate on the RUN path, the account_kind pin,
and the graceful fallback contract of run_search. These lock in FIX: SEARCH-1/2/3 —
a premium search model must not be usable by a non-premium user, an explicit backend
pin must be respected, and a failed configured model must fall back instead of erroring."""
from __future__ import annotations

from core.ai_router import search_adapter as sa
from core.ai_router.base import ProviderUnavailable, TextResult
from core.models.ai_routing import AIModel


class _User:
    """Minimal stand-in for core.models.User (only the attrs run_search reads)."""
    def __init__(self, is_premium: bool, search_model: str | None = None,
                 selected_model: str = "gpt"):
        self.is_premium = is_premium
        self.search_model = search_model
        self.selected_model = selected_model


def _model(key: str, *, premium: bool = False, upstream: str | None = None,
           kind: str | None = None) -> AIModel:
    return AIModel(
        key=key, title=key, upstream_model=upstream or key, modality="text",
        premium=premium, search=True, account_kind=kind, enabled=True,
    )


# ---------- FIX: SEARCH-1 — premium gate on resolve/run ----------

async def test_free_user_never_resolves_a_premium_model_saved_earlier():
    # User picked a premium model while Premium, then Premium lapsed: the saved key must
    # NOT resolve to the paid model — they get the first free one instead.
    models = [_model("free"), _model("pro", premium=True)]
    u = _User(is_premium=False, search_model="pro")
    got = await sa.resolve_search_model(None, u, models)
    assert got is not None and got.key == "free"


async def test_free_user_default_skips_leading_premium_model():
    # Admin ordered a premium model first; a free user with no saved choice must skip it.
    models = [_model("pro", premium=True), _model("free")]
    u = _User(is_premium=False, search_model=None)
    got = await sa.resolve_search_model(None, u, models)
    assert got is not None and got.key == "free"


async def test_premium_user_keeps_their_premium_model():
    models = [_model("free"), _model("pro", premium=True)]
    u = _User(is_premium=True, search_model="pro")
    got = await sa.resolve_search_model(None, u, models)
    assert got is not None and got.key == "pro"


async def test_only_premium_models_returns_none_for_free_user():
    models = [_model("pro", premium=True)]
    u = _User(is_premium=False)
    assert await sa.resolve_search_model(None, u, models) is None


# ---------- FIX: SEARCH-3 — _is_perplexity respects account_kind ----------

def test_explicit_non_perplexity_kind_is_not_forced_to_perplexity():
    # upstream contains "sonar" but the admin pinned openrouter → route via the pool.
    m = _model("x", upstream="perplexity/sonar", kind="openrouter")
    assert sa._is_perplexity(m) is False


def test_explicit_perplexity_kind_is_perplexity():
    m = _model("x", upstream="sonar", kind="perplexity")
    assert sa._is_perplexity(m) is True


def test_upstream_heuristic_when_no_kind_pinned():
    assert sa._is_perplexity(_model("x", upstream="perplexity/sonar")) is True
    assert sa._is_perplexity(_model("x", upstream="openai/gpt-4o-search-preview")) is False


# ---------- FIX: SEARCH-2 — run_search falls back instead of surfacing ok=False ----------

async def test_run_search_falls_back_when_configured_model_returns_not_ok(monkeypatch):
    """A non-Perplexity search model returns TextResult(ok=False) (registry.chat never
    raises); run_search must fall through to Perplexity → the user's text model, not
    return the error."""
    model = _model("gptsearch", upstream="openai/gpt-4o-search-preview")

    async def fake_resolve(session, user, models=None):
        return model

    async def fake_ai_chat(key, query, **kw):
        if key == "gptsearch":
            return TextResult(text="", model=key, ok=False)   # configured model is down
        return TextResult(text="answer from text model", model=key, ok=True)

    async def fake_pplx(query, model="sonar"):
        raise ProviderUnavailable("perplexity")   # no Perplexity key configured

    monkeypatch.setattr(sa, "resolve_search_model", fake_resolve)
    monkeypatch.setattr(sa, "ai_chat", fake_ai_chat)
    monkeypatch.setattr(sa, "perplexity_search", fake_pplx)

    u = _User(is_premium=True, selected_model="mytext")
    res = await sa.run_search(None, u, "q", system="s")
    assert res.ok and res.text == "answer from text model"


async def test_run_search_returns_a_successful_configured_result_directly(monkeypatch):
    model = _model("gptsearch", upstream="openai/gpt-4o-search-preview")

    async def fake_resolve(session, user, models=None):
        return model

    async def fake_ai_chat(key, query, **kw):
        return TextResult(text="direct web answer", model=key, ok=True)

    monkeypatch.setattr(sa, "resolve_search_model", fake_resolve)
    monkeypatch.setattr(sa, "ai_chat", fake_ai_chat)

    u = _User(is_premium=True)
    res = await sa.run_search(None, u, "q", system="s")
    assert res.ok and res.text == "direct web answer"
