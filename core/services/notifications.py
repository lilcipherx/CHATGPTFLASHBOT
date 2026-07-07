"""User-facing notifications sent from outside the bot's normal handler flow —
admin actions (premium gifted/revoked, ban/unban) and contact capture.

Delivery is best-effort: a user who has blocked the bot, or any Telegram error,
must never break the admin action that triggered the notice, so every send is
wrapped and failures are swallowed (logged)."""
from __future__ import annotations

import logging

from core.bot_client import get_bot
from core.i18n import t

logger = logging.getLogger(__name__)

# Country calling code (longest-prefix match) -> ISO-3166 alpha-2. CIS audience is
# first, then a broad set of common calling codes so most shared phones resolve.
# Longest-prefix wins (e.g. "998" before "9", "380" before "3"); unknown -> None.
# NANP (+1) defaults to US — area-code-level disambiguation isn't worth it here.
_PHONE_CC: dict[str, str] = {
    # CIS / neighbours
    "7": "RU", "77": "KZ", "76": "KZ",
    "998": "UZ", "996": "KG", "992": "TJ", "993": "TM", "994": "AZ",
    "374": "AM", "995": "GE", "375": "BY", "380": "UA", "373": "MD",
    # +1 NANP
    "1": "US",
    # Europe
    "44": "GB", "49": "DE", "33": "FR", "34": "ES", "39": "IT", "351": "PT",
    "31": "NL", "32": "BE", "41": "CH", "43": "AT", "48": "PL", "420": "CZ",
    "421": "SK", "36": "HU", "40": "RO", "359": "BG", "30": "GR", "385": "HR",
    "386": "SI", "381": "RS", "382": "ME", "389": "MK", "355": "AL",
    "353": "IE", "352": "LU", "356": "MT", "357": "CY", "354": "IS",
    "45": "DK", "46": "SE", "47": "NO", "358": "FI", "372": "EE", "371": "LV",
    "370": "LT", "377": "MC", "378": "SM", "423": "LI", "376": "AD",
    # Middle East
    "90": "TR", "972": "IL", "971": "AE", "966": "SA", "974": "QA", "973": "BH",
    "965": "KW", "968": "OM", "962": "JO", "961": "LB", "963": "SY", "964": "IQ",
    "98": "IR", "967": "YE", "970": "PS",
    # Asia
    "91": "IN", "86": "CN", "81": "JP", "82": "KR", "84": "VN", "66": "TH",
    "60": "MY", "65": "SG", "62": "ID", "63": "PH", "92": "PK", "880": "BD",
    "94": "LK", "95": "MM", "977": "NP", "856": "LA", "855": "KH", "852": "HK",
    "853": "MO", "886": "TW", "976": "MN", "93": "AF",
    # Africa
    "20": "EG", "212": "MA", "213": "DZ", "216": "TN", "218": "LY", "234": "NG",
    "254": "KE", "256": "UG", "255": "TZ", "233": "GH", "251": "ET", "27": "ZA",
    "225": "CI", "221": "SN", "237": "CM", "244": "AO", "260": "ZM", "263": "ZW",
    # Americas
    "52": "MX", "55": "BR", "54": "AR", "56": "CL", "57": "CO", "58": "VE",
    "51": "PE", "593": "EC", "591": "BO", "595": "PY", "598": "UY", "507": "PA",
    "506": "CR", "502": "GT", "504": "HN", "503": "SV", "505": "NI", "53": "CU",
    # Oceania
    "61": "AU", "64": "NZ",
}


def country_from_phone(phone: str | None) -> str | None:
    """Best-effort ISO alpha-2 country from a phone's calling code."""
    if not phone:
        return None
    digits = "".join(ch for ch in phone if ch.isdigit())
    if not digits:
        return None
    # Longest matching prefix wins (e.g. "998" before "9", "77" before "7").
    for length in (4, 3, 2, 1):
        if len(digits) >= length and digits[:length] in _PHONE_CC:
            return _PHONE_CC[digits[:length]]
    return None


async def notify_user(user_id: int, key: str, locale: str = "ru", **kwargs) -> bool:
    """Send a localized message to a user. Returns True on success, never raises."""
    try:
        await get_bot().send_message(user_id, t(key, locale, **kwargs))
        return True
    except Exception:  # noqa: BLE001 — blocked bot / network: must not break caller
        logger.warning("notify_user failed for %s key=%s", user_id, key, exc_info=True)
        return False
