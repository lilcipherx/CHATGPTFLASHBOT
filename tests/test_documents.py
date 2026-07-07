"""Document extraction (txt/csv need no third-party parser) + ext detection."""
from __future__ import annotations

import pytest

from core.services.documents import (
    SUPPORTED_EXT,
    UnsupportedDocument,
    ext_of,
    extract_text,
)


def test_ext_detection():
    assert ext_of("report.PDF") == "pdf"
    assert ext_of("data.tar.gz") == "gz"
    assert ext_of("noext") == ""


def test_txt_extraction():
    assert extract_text("a.txt", "привет мир".encode()) == "привет мир"


def test_csv_extraction():
    out = extract_text("a.csv", b"name,age\nAna,30")
    assert "name\tage" in out
    assert "Ana\t30" in out


def test_unsupported_raises():
    with pytest.raises(UnsupportedDocument):
        extract_text("a.exe", b"x")


def test_supported_set():
    assert {"pdf", "docx", "xlsx", "csv", "txt", "pptx"} <= SUPPORTED_EXT
