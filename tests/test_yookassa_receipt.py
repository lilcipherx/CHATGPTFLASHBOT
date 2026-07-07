"""54-ФЗ fiscal receipt builder for YooKassa checkout requests."""
from __future__ import annotations

import pytest

from core.config import settings
from core.payments.yookassa_gw import _build_receipt


@pytest.fixture
def receipt_on(monkeypatch):
    """Enable receipts with an email contact and a known vat_code."""
    monkeypatch.setattr(settings, "yookassa_receipt_enabled", True)
    monkeypatch.setattr(settings, "yookassa_vat_code", 4)
    monkeypatch.setattr(settings, "yookassa_tax_system_code", None)
    monkeypatch.setattr(settings, "yookassa_receipt_contact", "buyer@example.com")


def test_omitted_when_disabled():
    # Default: master switch off -> no receipt regardless of other settings.
    assert _build_receipt(60000, "RUB", "Premium 3m") is None


def test_omitted_for_non_rub(receipt_on):
    assert _build_receipt(60000, "USD", "Premium 3m") is None


def test_present_and_well_formed(receipt_on):
    r = _build_receipt(60000, "RUB", "Premium 3m")
    assert r is not None
    item = r["items"][0]
    assert item["amount"]["value"] == "600.00"
    assert item["amount"]["currency"] == "RUB"
    assert item["quantity"] == "1.00"
    assert item["vat_code"] == 4
    assert item["payment_mode"] == "full_prepayment"
    assert item["payment_subject"] == "service"
    assert r["customer"] == {"email": "buyer@example.com"}


def test_description_truncated_to_128(receipt_on):
    long_desc = "x" * 200
    r = _build_receipt(60000, "RUB", long_desc)
    assert len(r["items"][0]["description"]) == 128


def test_phone_branch(monkeypatch, receipt_on):
    monkeypatch.setattr(settings, "yookassa_receipt_contact", "+7 (999) 123-45-67")
    r = _build_receipt(60000, "RUB", "Premium 3m")
    assert r["customer"] == {"phone": "79991234567"}


def test_tax_system_code_omitted_when_unset(receipt_on):
    r = _build_receipt(60000, "RUB", "Premium 3m")
    assert "tax_system_code" not in r


def test_tax_system_code_present_when_set(monkeypatch, receipt_on):
    monkeypatch.setattr(settings, "yookassa_tax_system_code", 2)
    r = _build_receipt(60000, "RUB", "Premium 3m")
    assert r["tax_system_code"] == 2
