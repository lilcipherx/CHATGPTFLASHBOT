"""External payment gateway registry (Stars is native in the bot)."""
from core.payments.base import (
    CheckoutResult,
    PaymentError,
    PaymentEvent,
    PaymentProvider,
    PaymentRetryable,
)
from core.payments.crypto_gw import CryptoBotProvider
from core.payments.stripe_gw import StripeProvider
from core.payments.tribute_gw import TributeProvider
from core.payments.yookassa_gw import YooKassaProvider

_PROVIDERS: dict[str, PaymentProvider] = {
    "yookassa": YooKassaProvider(),
    "stripe": StripeProvider(),
    "sbp_tribute": TributeProvider(),
    "crypto": CryptoBotProvider(),
}


def get_provider(gateway: str) -> PaymentProvider | None:
    return _PROVIDERS.get(gateway)


__all__ = [
    "CheckoutResult",
    "PaymentError",
    "PaymentEvent",
    "PaymentProvider",
    "PaymentRetryable",
    "get_provider",
]
