"""External payment gateways: registry, availability, Stars→fiat conversion."""
from __future__ import annotations

from core.config import settings
from core.payments import get_provider
from core.payments.service import stars_to_minor


def test_registry_has_three_gateways():
    assert get_provider("yookassa").name == "yookassa"
    assert get_provider("stripe").name == "stripe"
    assert get_provider("sbp_tribute").name == "sbp_tribute"
    assert get_provider("unknown") is None


def test_gateways_unavailable_without_keys():
    for gw in ("yookassa", "stripe", "sbp_tribute"):
        assert get_provider(gw).is_available() is False


def test_stars_to_minor_currency_split():
    # 600⭐ premium -> RUB kopecks for yookassa/tribute, USD cents for stripe
    rub, cur = stars_to_minor(600, "yookassa")
    assert cur == "RUB"
    assert rub == int(round(600 * settings.stars_to_rub * 100))

    usd, cur = stars_to_minor(600, "stripe")
    assert cur == "USD"
    assert usd == int(round(600 * settings.stars_to_usd * 100))
