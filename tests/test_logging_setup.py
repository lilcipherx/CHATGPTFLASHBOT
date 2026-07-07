"""core.logging_setup — console + rotating file handler so the Maintenance Log
Center (which tails settings.log_file) actually has content to show."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

import core.logging_setup as ls


def _reset_root():
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    ls._CONFIGURED = False


def test_setup_adds_console_and_rotating_file(tmp_path, monkeypatch):
    _reset_root()
    log_file = tmp_path / "logs" / "app.log"
    monkeypatch.setattr(ls.settings, "log_file", str(log_file), raising=False)
    monkeypatch.setattr(ls.settings, "log_level", "INFO", raising=False)

    ls.setup_logging()
    root = logging.getLogger()
    handlers = root.handlers
    assert any(isinstance(h, RotatingFileHandler) for h in handlers), "file handler missing"
    assert any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in handlers
    ), "console handler missing"

    # A log line actually lands in the file (severity word present for the UI parser).
    logging.getLogger("test.logger").error("hello maintenance")
    for h in handlers:
        h.flush()
    assert log_file.is_file()
    content = log_file.read_text(encoding="utf-8")
    assert "hello maintenance" in content
    assert "ERROR" in content
    _reset_root()


def test_setup_is_idempotent(tmp_path, monkeypatch):
    _reset_root()
    monkeypatch.setattr(ls.settings, "log_file", str(tmp_path / "a.log"), raising=False)
    ls.setup_logging()
    n = len(logging.getLogger().handlers)
    ls.setup_logging()  # second call must not duplicate handlers
    assert len(logging.getLogger().handlers) == n
    _reset_root()


def test_setup_survives_unwritable_path(monkeypatch):
    _reset_root()
    # A path under a file (not a dir) makes makedirs/open fail — must not raise.
    monkeypatch.setattr(ls.settings, "log_file", "\0bad/app.log", raising=False)
    ls.setup_logging()  # should swallow OSError and keep console logging
    assert any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in logging.getLogger().handlers
    )
    _reset_root()
