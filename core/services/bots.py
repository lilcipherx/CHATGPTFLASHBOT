"""Multi-bot / white-label service (ТЗ §0).

Manages the BotInstance registry and a process-local map from a Telegram bot id to
its BotInstance id, so the bot middleware can stamp ``User.bot_id`` (tenant
attribution) without a DB hit per update. Tokens are encrypted at rest.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.bot_instance import BotInstance
from core.services.crypto import decrypt, encrypt

# Process-local {telegram_bot_id: bot_instance_id}, filled by the launcher /
# load_bot_map. Empty in a single-bot deployment → bot_id stays NULL (legacy).
_BOT_MAP: dict[int, int] = {}


def bot_id_for(tg_bot_id: int | None) -> int | None:
    """Map a Telegram bot id to its BotInstance id (None when unknown/single-bot)."""
    if tg_bot_id is None:
        return None
    return _BOT_MAP.get(tg_bot_id)


def register_bot(tg_bot_id: int, instance_id: int) -> None:
    _BOT_MAP[tg_bot_id] = instance_id


def clear_map() -> None:
    _BOT_MAP.clear()


async def load_bot_map(session: AsyncSession) -> dict[int, int]:
    """(Re)load the tg_bot_id → instance_id map from instances that have connected."""
    rows = (await session.scalars(
        select(BotInstance).where(BotInstance.tg_bot_id.is_not(None))
    )).all()
    _BOT_MAP.clear()
    for b in rows:
        if b.tg_bot_id is not None:
            _BOT_MAP[b.tg_bot_id] = b.id
    return dict(_BOT_MAP)


@dataclass
class LaunchSpec:
    """A bot ready to launch: instance id + decrypted token."""
    instance_id: int
    title: str
    token: str


async def list_bots(session: AsyncSession) -> list[BotInstance]:
    return list(await session.scalars(
        select(BotInstance).order_by(BotInstance.is_default.desc(), BotInstance.id)
    ))


async def get_bot(session: AsyncSession, bot_id: int) -> BotInstance | None:
    return await session.get(BotInstance, bot_id)


async def token_in_use(
    session: AsyncSession, token: str, *, exclude_id: int | None = None
) -> bool:
    """True if `token` (plaintext) is already registered on another instance. Two
    instances polling the SAME token make Telegram return 409 Conflict and BOTH
    stop receiving updates — so we reject the duplicate up front. Ciphertext is
    non-deterministic (Fernet), so we decrypt-and-compare."""
    token = (token or "").strip()
    if not token:
        return False
    for b in await session.scalars(select(BotInstance)):
        if exclude_id is not None and b.id == exclude_id:
            continue
        if decrypt(b.token) == token:
            return True
    return False


async def verify_token(token: str) -> dict:
    """Probe a Telegram bot token via getMe — a single read-only Bot API call, NOT
    polling (no getUpdates), so it never competes with a running launcher. Returns
    {ok, tg_bot_id, username, name, status_code, latency_ms, detail}."""
    import time

    import httpx

    token = (token or "").strip()
    base = {"ok": False, "tg_bot_id": None, "username": None, "name": None}
    if ":" not in token:
        return {**base, "status_code": 0, "latency_ms": 0, "detail": "неверный формат токена"}
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            r = await http.get(f"https://api.telegram.org/bot{token}/getMe")
        lat = int((time.monotonic() - t0) * 1000)
        try:
            data = r.json()
        except Exception:  # noqa: BLE001
            data = {}
        if r.status_code < 400 and isinstance(data, dict) and data.get("ok"):
            res = data.get("result") or {}
            return {"ok": True, "tg_bot_id": res.get("id"), "username": res.get("username"),
                    "name": res.get("first_name"), "status_code": r.status_code,
                    "latency_ms": lat, "detail": ""}
        detail = (
            (data.get("description") if isinstance(data, dict) else None)
            or (r.text or "")[:200]
        )
        return {**base, "status_code": r.status_code, "latency_ms": lat, "detail": detail}
    except Exception as exc:  # noqa: BLE001 — any transport error = unreachable
        return {**base, "status_code": 0,
                "latency_ms": int((time.monotonic() - t0) * 1000), "detail": str(exc)[:200]}


async def active_launch_specs(session: AsyncSession) -> list[LaunchSpec]:
    """Active instances with their tokens decrypted, for the launcher."""
    rows = (await session.scalars(
        select(BotInstance).where(BotInstance.active.is_(True)).order_by(BotInstance.id)
    )).all()
    out = []
    for b in rows:
        tok = decrypt(b.token)
        if tok:
            out.append(LaunchSpec(instance_id=b.id, title=b.title, token=tok))
    return out


async def create_bot(
    session: AsyncSession, *, title: str, token: str, is_default: bool = False
) -> BotInstance:
    if is_default:
        await _clear_default(session)
    b = BotInstance(title=title, token=encrypt(token), is_default=is_default)
    session.add(b)
    await session.commit()
    await session.refresh(b)
    return b


async def update_bot(
    session: AsyncSession, bot_id: int, *,
    title: str | None = None, token: str | None = None,
    active: bool | None = None, is_default: bool | None = None,
) -> BotInstance | None:
    b = await session.get(BotInstance, bot_id)
    if b is None:
        return None
    if title is not None:
        b.title = title
    if token:  # empty = keep existing
        b.token = encrypt(token)
    if active is not None:
        b.active = active
    if is_default:
        await _clear_default(session)
        b.is_default = True
    await session.commit()
    await session.refresh(b)
    return b


async def delete_bot(session: AsyncSession, bot_id: int) -> bool:
    b = await session.get(BotInstance, bot_id)
    if b is None:
        return False
    await session.delete(b)
    await session.commit()
    return True


async def record_identity(
    session: AsyncSession, bot_id: int, *, tg_bot_id: int, username: str | None
) -> None:
    """Persist the Telegram identity discovered via get_me() on first launch."""
    b = await session.get(BotInstance, bot_id)
    if b is None:
        return
    b.tg_bot_id = tg_bot_id
    b.username = username
    await session.commit()


async def _clear_default(session: AsyncSession) -> None:
    for b in await session.scalars(select(BotInstance).where(BotInstance.is_default.is_(True))):
        b.is_default = False
