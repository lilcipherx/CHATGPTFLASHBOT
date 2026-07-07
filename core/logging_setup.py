"""Central logging configuration — console + a size-rotating file handler.

The admin Maintenance «Log Center» tails ``settings.log_file`` (default
``logs/app.log``), so the application must actually WRITE there. This helper wires
the root logger to both stdout (unchanged behaviour) and a rotating file, and is
called from every process entrypoint (API, bot, workers). Best-effort: a
file-system problem (read-only FS, missing perms) never blocks startup — console
logging keeps working.
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

from core.config import settings

_CONFIGURED = False
_FMT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB per file before rotation
_BACKUPS = 5                   # keep app.log + app.log.1 … app.log.5


def setup_logging() -> None:
    """Configure root logging ONCE: a console handler plus a rotating file handler
    writing to ``settings.log_file``. Idempotent — safe to call from multiple
    entrypoints / imports."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = getattr(logging, str(settings.log_level).upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    fmt = logging.Formatter(_FMT)

    # Console handler (preserve the prior basicConfig behaviour). A FileHandler is
    # itself a StreamHandler subclass, so exclude it from this check.
    has_console = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in root.handlers
    )
    if not has_console:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)

    # Rotating file handler → settings.log_file, for the Maintenance Log Center.
    path = (settings.log_file or "").strip()
    if path and not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        try:
            d = os.path.dirname(os.path.abspath(path))
            if d:
                os.makedirs(d, exist_ok=True)
            fh = RotatingFileHandler(
                path, maxBytes=_MAX_BYTES, backupCount=_BACKUPS, encoding="utf-8"
            )
            fh.setFormatter(fmt)
            root.addHandler(fh)
        except (OSError, ValueError) as exc:  # read-only FS / perms / bad path — keep console only
            logging.getLogger(__name__).warning(
                "file logging disabled (cannot write %s): %s", path, exc
            )

    _CONFIGURED = True
