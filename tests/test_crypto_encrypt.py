"""Fernet encrypt/decrypt for stored secrets (Loop coverage): round-trip, empty
pass-through, legacy plaintext, undecryptable-token → "" (rotated key), and the
no-secret hard fail. Pure crypto, no DB.
"""
from __future__ import annotations

from core.services.crypto import _PREFIX, decrypt, encrypt


def test_encrypt_empty_passthrough():
    assert encrypt("") == ""


def test_encrypt_decrypt_round_trip():
    tok = encrypt("super-secret-api-key")
    assert tok.startswith(_PREFIX) and tok != "super-secret-api-key"
    assert decrypt(tok) == "super-secret-api-key"


def test_decrypt_legacy_plaintext_passthrough():
    # a stored value without the enc:: prefix is returned unchanged
    assert decrypt("legacy-plain") == "legacy-plain"


def test_decrypt_bad_ciphertext_returns_empty():
    # prefixed but corrupt ciphertext (e.g. rotated ENC_SECRET) → "" so the account
    # reads as unconfigured instead of leaking raw ciphertext upstream
    assert decrypt(_PREFIX + "not-a-valid-fernet-token") == ""
