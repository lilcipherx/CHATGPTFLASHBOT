"""Router-container management (ТЗ §2) — superadmin-controlled ``docker compose``
ops for the self-hosted router containers (LiteLLM).

SAFETY (this is host access, so it is deliberately narrow):
* the whole feature is gated behind ``settings.router_mgmt_enabled`` (off by default);
* only the fixed :data:`ROUTER_SERVICES` allowlist is ever passed to docker — the
  service name is validated *before* any call, so no arbitrary container is reachable;
* argv is always a fixed list (``create_subprocess_exec``, never a shell string), so
  there is no command injection even if a service name slipped through;
* every call has a timeout, and log tails are clamped.

``_run`` is the single subprocess boundary, so tests stub it out and no real docker
daemon is needed.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from core.config import settings

# The router containers a superadmin may control. NOTHING outside this set is
# reachable — see _ensure(). Add other self-hosted router service names here as the
# compose stack grows.
ROUTER_SERVICES: tuple[str, ...] = ("litellm",)

# start | stop | restart — the only lifecycle verbs exposed.
ACTIONS: tuple[str, ...] = ("start", "stop", "restart")

_LOGS_MAX_TAIL = 2000
# docker can wedge (pull, daemon hang) — cap every call so an endpoint never blocks.
_CMD_TIMEOUT = 30


class RouterMgmtDisabled(RuntimeError):
    """``settings.router_mgmt_enabled`` is off — the feature is inert."""


class UnknownRouter(ValueError):
    """Service is not in the :data:`ROUTER_SERVICES` allowlist."""


@dataclass
class CmdResult:
    ok: bool
    code: int
    stdout: str
    stderr: str


def is_enabled() -> bool:
    return bool(settings.router_mgmt_enabled)


def _ensure(service: str) -> None:
    """Gate every operation: feature must be enabled and the service allowlisted."""
    if not is_enabled():
        raise RouterMgmtDisabled("router management is disabled")
    if service not in ROUTER_SERVICES:
        raise UnknownRouter(service)


async def _run(args: list[str]) -> CmdResult:
    """Run ``docker compose <args>`` with a fixed argv (no shell) and a timeout.

    Single point of contact with the host; tests monkeypatch this."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "compose", *args,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return CmdResult(False, -1, "", "docker not found on host")
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=_CMD_TIMEOUT)
    except TimeoutError:
        proc.kill()
        return CmdResult(False, -1, "", "docker compose timed out")
    return CmdResult(
        proc.returncode == 0,
        proc.returncode if proc.returncode is not None else 0,
        (out or b"").decode("utf-8", "replace"),
        (err or b"").decode("utf-8", "replace"),
    )


async def status(service: str) -> CmdResult:
    """`docker compose ps <service>` — running/stopped + ports."""
    _ensure(service)
    return await _run(["ps", service])


async def action(service: str, verb: str) -> CmdResult:
    """start | stop | restart the given router service."""
    _ensure(service)
    if verb not in ACTIONS:
        raise ValueError(f"unsupported action: {verb}")
    return await _run([verb, service])


async def logs(service: str, tail: int = 200) -> CmdResult:
    """Last ``tail`` (clamped) log lines of the router container."""
    _ensure(service)
    tail = max(1, min(tail, _LOGS_MAX_TAIL))
    return await _run(["logs", "--no-color", "--tail", str(tail), service])
