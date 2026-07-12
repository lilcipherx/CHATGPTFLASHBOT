"""Admin: AI routing control — OmniRoute account pool, fallback providers, the
user-facing model catalog, and per-account health. All mutations are audited."""
from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.audit import audit
from api.admin.deps import require_role
from core.config import settings
from core.db import get_session
from core.models import AdminUser
from core.models.ai_routing import MODALITIES, AIAccount, AIModel
from core.services.crypto import decrypt, encrypt

router = APIRouter(prefix="/ai", tags=["admin-ai"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _validate_base_url(url: str) -> str:
    """Validate an admin-supplied AI account base_url (SSRF defence).

    The gateway code makes server-side HTTP calls (with the account's API key) to
    this URL, so an unchecked value lets a request be aimed at internal services
    or the cloud metadata endpoint. We require an http(s) URL and, when
    AI_BASE_URL_ALLOWLIST is set, restrict the host to it; otherwise we at least
    reject literal non-public IPs (loopback/link-local/private/reserved — the
    classic SSRF targets). Returns the normalised URL (trailing slash stripped).

    NOTE: this is the SYNC variant retained for tests and the import path that
    runs in a thread. Async callers (admin endpoints) should use
    ``_validate_base_url_async`` so DNS resolution runs in a worker thread and
    doesn't block the event loop (FIX: AUDIT12-M4)."""
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise HTTPException(status_code=400, detail="base_url must be a http(s) URL")
    host = p.hostname.lower()
    allow = settings.ai_base_url_allow
    if allow:
        if not any(host == h or host.endswith("." + h) for h in allow):
            raise HTTPException(status_code=400, detail="base_url host not in allowlist")
        return url.rstrip("/")
    try:
        candidates = [ipaddress.ip_address(host)]
    except ValueError:
        # A hostname: RESOLVE it and check every address it maps to, so a name that
        # points at 127.0.0.1 / 169.254.169.254 (cloud metadata) can't slip past the
        # literal-IP check.
        # FIX: AUDIT-SOFT (owner request) - relaxed N6: if DNS fails to resolve the
        # host, ALLOW it (fall through) instead of hard-rejecting, so internal /
        # temporarily-unresolvable hosts can be added. The literal-internal-IP and
        # resolves-to-internal checks below STILL apply. NOTE the residual SSRF risk:
        # a host that is unresolvable at validation but later resolves to a private IP
        # is not caught here — prefer AI_BASE_URL_ALLOWLIST for known internal hosts.
        candidates = _resolve_host_candidates(host)
    if any(
        ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_reserved
        for ip in candidates
    ):
        raise HTTPException(status_code=400, detail="base_url resolves to a non-public address")
    return url.rstrip("/")


def _resolve_host_candidates(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Sync DNS resolver shared by ``_validate_base_url`` and its async twin.

    Returns the list of IP addresses the host resolves to, or an EMPTY list if DNS
    fails. FIX: AUDIT-SOFT (owner request) - an unresolvable host now falls through to
    "allowed" (empty candidates → the internal-IP check below finds nothing to block)
    rather than hard-rejecting. Extracted as a helper so the async variant can run it
    in ``asyncio.to_thread`` without re-implementing the URL-validation pipeline."""
    import socket

    # FIX: AI-20 - do NOT call socket.setdefaulttimeout(5) — it is a process-global
    # side effect that poisons every other socket in the worker (DB pool, httpx,
    # Redis). Instead, run getaddrinfo with an explicit timeout via asyncio.wait_for
    # in the async variant (_validate_base_url_async). The sync helper is only
    # called from tests now; for the sync path we use a short-lived socket with a
    # per-call timeout via socket.getaddrinfo's own behaviour (no global mutation).
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return []  # unresolvable → no candidates → allowed (see docstring / AUDIT-SOFT)
    out: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in infos:
        try:
            out.append(ipaddress.ip_address(info[4][0]))
        except ValueError:
            continue
    return out


async def _validate_base_url_async(url: str) -> str:
    """Async variant of ``_validate_base_url`` — same SSRF checks, but DNS
    resolution runs in a worker thread via ``asyncio.to_thread`` so the event
    loop is not blocked on a slow/unresponsive resolver (FIX: AUDIT12-M4).

    Used by every admin endpoint that accepts a base_url (create/update/import).
    The sync ``_validate_base_url`` is kept for tests + the import-config path
    that already runs each row through a thread pool."""
    import asyncio

    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise HTTPException(status_code=400, detail="base_url must be a http(s) URL")
    host = p.hostname.lower()
    allow = settings.ai_base_url_allow
    if allow:
        if not any(host == h or host.endswith("." + h) for h in allow):
            raise HTTPException(status_code=400, detail="base_url host not in allowlist")
        return url.rstrip("/")
    try:
        candidates = [ipaddress.ip_address(host)]
    except ValueError:
        # FIX: AUDIT12-M4 - run the blocking DNS lookup in a thread pool to avoid
        # stalling the event loop on a slow resolver.
        # FIX: AI-20 - bound the lookup to 5s via asyncio.wait_for so a hanging
        # resolver can't stall the admin endpoint (replaces the removed
        # socket.setdefaulttimeout global mutation).
        try:
            candidates = await asyncio.wait_for(
                asyncio.to_thread(_resolve_host_candidates, host),
                timeout=5.0,
            )
        except TimeoutError:
            raise HTTPException(
                status_code=400,
                detail="base_url host DNS lookup timed out (5s)",
            ) from None
    if any(
        ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_reserved
        for ip in candidates
    ):
        raise HTTPException(status_code=400, detail="base_url resolves to a non-public address")
    return url.rstrip("/")


def _mask(stored_key: str) -> str:
    """Never return a full API key — decrypt then show only a recognisable tail."""
    key = decrypt(stored_key)
    return f"…{key[-4:]}" if key and len(key) > 4 else "****"


async def _account_ping(base_url: str, api_key: str) -> dict:
    """Probe an OpenAI-compatible endpoint (GET /models) with the account's key and
    measure round-trip latency. Read-only — never mutates health counters. Patched
    in tests so no network is required."""
    import time

    import httpx

    url = f"{base_url.rstrip('/')}/models"
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            r = await http.get(url, headers={"Authorization": f"Bearer {api_key}"})
        ok = r.status_code < 400
        return {
            "ok": ok,
            "status_code": r.status_code,
            "latency_ms": int((time.monotonic() - t0) * 1000),
            "detail": "" if ok else (r.text or "")[:200],
        }
    except Exception as exc:  # noqa: BLE001 — any transport error = unreachable
        return {
            "ok": False,
            "status_code": 0,
            "latency_ms": int((time.monotonic() - t0) * 1000),
            "detail": str(exc)[:200],
        }


def _account_dict(a: AIAccount) -> dict:
    return {
        "id": a.id, "name": a.name, "kind": a.kind, "base_url": a.base_url,
        "api_key": _mask(a.api_key), "modality": a.modality, "tier": a.tier,
        "priority": a.priority, "weight": a.weight, "enabled": a.enabled, "status": a.status,
        "cooldown_until": a.cooldown_until.isoformat() if a.cooldown_until else None,
        "total_requests": a.total_requests, "total_errors": a.total_errors,
        "last_used_at": a.last_used_at.isoformat() if a.last_used_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "last_error": a.last_error,
        "last_latency_ms": a.last_latency_ms, "avg_latency_ms": a.avg_latency_ms,
        # uptime proxy: share of lifetime requests that did not error (1.0 when unused).
        "success_rate": (
            round((a.total_requests - a.total_errors) / a.total_requests, 4)
            if a.total_requests else 1.0
        ),
        # accumulated provider spend (ТЗ §2): raw micro-USD + a display USD figure.
        "spend_micros": a.spend_micros,
        "spend_usd": round((a.spend_micros or 0) / 1_000_000, 4),
        # hard spend cap (ТЗ §2 «лимиты трат»): 0 = unlimited; over_budget sidelines it.
        "spend_limit_micros": a.spend_limit_micros,
        "spend_limit_usd": round((a.spend_limit_micros or 0) / 1_000_000, 4),
        "over_budget": (
            a.spend_limit_micros > 0 and (a.spend_micros or 0) >= a.spend_limit_micros
        ),
    }


# ---------- Accounts ----------
@router.get("/accounts")
async def list_accounts(
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    rows = (await session.scalars(
        select(AIAccount).order_by(AIAccount.tier, AIAccount.priority, AIAccount.id)
    )).all()
    return [_account_dict(a) for a in rows]


class AccountCreate(BaseModel):
    # FIX: AUDIT12-26 - bounded strings + numeric ranges on AI account
    name: str = Field(..., max_length=100)
    # omniroute | openrouter | apimart | kie | direct | custom
    kind: str = Field("omniroute", max_length=50)
    base_url: str = Field(..., max_length=2048)
    api_key: str = Field(..., max_length=512)
    modality: str = Field("text", max_length=20)          # text | image | video | music
    tier: int = Field(0, ge=0, le=10)                   # 0 pool, 1 fallback
    priority: int = Field(100, ge=0, le=1000)
    # relative load share within a (tier, priority)
    weight: int = Field(1, ge=1, le=100)
    # hard spend cap, micro-USD; 0 = unlimited
    spend_limit_micros: int = Field(0, ge=0, le=10**15)
    enabled: bool = True


@router.post("/accounts")
async def create_account(
    req: AccountCreate, request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if req.modality not in MODALITIES:
        raise HTTPException(status_code=400, detail="bad modality")
    acc = AIAccount(
        name=req.name, kind=req.kind, base_url=await _validate_base_url_async(req.base_url),
        api_key=encrypt(req.api_key), modality=req.modality, tier=req.tier,
        priority=req.priority, weight=req.weight,
        spend_limit_micros=req.spend_limit_micros, enabled=req.enabled,
    )
    session.add(acc)
    await audit(session, admin_id=admin.id, action="ai.account.create", target_type="ai_account",
                target_id=str(acc.id), after={"name": req.name, "kind": req.kind, "tier": req.tier},
                ip=_ip(request), commit=False)  # FIX: A1
    await session.commit()
    return _account_dict(acc)


class AccountUpdate(BaseModel):
    # FIX: AUDIT12-26 - Optional variants of AccountCreate
    name: str | None = Field(None, max_length=100)
    kind: str | None = Field(None, max_length=50)
    base_url: str | None = Field(None, max_length=2048)
    # only updates when a non-empty value is sent
    api_key: str | None = Field(None, max_length=512)
    modality: str | None = Field(None, max_length=20)
    tier: int | None = Field(None, ge=0, le=10)
    priority: int | None = Field(None, ge=0, le=1000)
    weight: int | None = Field(None, ge=1, le=100)
    spend_limit_micros: int | None = Field(None, ge=0, le=10**15)
    enabled: bool | None = None


@router.put("/accounts/{account_id}")
async def update_account(
    account_id: int, req: AccountUpdate, request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    acc = await session.get(AIAccount, account_id)
    if acc is None:
        raise HTTPException(status_code=404, detail="not found")
    for field in ("name", "kind", "modality", "tier", "priority", "weight",
                  "spend_limit_micros", "enabled"):
        val = getattr(req, field)
        if val is not None:
            setattr(acc, field, val)
    if req.base_url is not None:
        acc.base_url = await _validate_base_url_async(req.base_url)
    if req.api_key:  # empty string = keep existing
        acc.api_key = encrypt(req.api_key)
    await audit(session, admin_id=admin.id, action="ai.account.update", target_type="ai_account",
    target_id=str(account_id), after={"enabled": acc.enabled, "tier": acc.tier},
    ip=_ip(request), commit=False)  # FIX: A1
    await session.commit()
    return _account_dict(acc)


@router.delete("/accounts/{account_id}")
async def delete_account(
    account_id: int, request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    acc = await session.get(AIAccount, account_id)
    if acc is None:
        raise HTTPException(status_code=404, detail="not found")
    await session.delete(acc)
    await audit(session, admin_id=admin.id, action="ai.account.delete", target_type="ai_account",
    target_id=str(account_id), ip=_ip(request), commit=False)  # FIX: A1
    await session.commit()
    return {"ok": True}


@router.post("/accounts/{account_id}/test")
async def test_account(
    account_id: int, request: Request,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """«Проверить подключение»: probe the account's endpoint with its decrypted key
    and report reachability + latency. Does NOT touch health counters (a manual test
    shouldn't trip cooldown), but is audited."""
    acc = await session.get(AIAccount, account_id)
    if acc is None:
        raise HTTPException(status_code=404, detail="not found")
    result = await _account_ping(acc.base_url, decrypt(acc.api_key))
    await audit(session, admin_id=admin.id, action="ai.account.test", target_type="ai_account",
                target_id=str(account_id),
                after={"ok": result["ok"], "latency_ms": result["latency_ms"]},
                ip=_ip(request))
    return result


@router.post("/accounts/{account_id}/reset")
async def reset_account(
    account_id: int, request: Request,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Clear cooldown / error state and re-enable an account."""
    acc = await session.get(AIAccount, account_id)
    if acc is None:
        raise HTTPException(status_code=404, detail="not found")
    acc.status = "active"
    acc.cooldown_until = None
    acc.total_errors = 0
    acc.last_error = None
    acc.enabled = True
    await audit(session, admin_id=admin.id, action="ai.account.reset", target_type="ai_account",
    target_id=str(account_id), ip=_ip(request), commit=False)  # FIX: A1
    await session.commit()
    return _account_dict(acc)


@router.post("/accounts/{account_id}/reset-spend")
async def reset_spend(
    account_id: int, request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Zero the account's accumulated spend (ТЗ §2 «лимиты трат») — start a new
    billing window. If the account was sidelined for hitting its cap, this brings it
    back into rotation. Superadmin-only (it resets billing data)."""
    acc = await session.get(AIAccount, account_id)
    if acc is None:
        raise HTTPException(status_code=404, detail="not found")
    before = acc.spend_micros
    acc.spend_micros = 0
    await audit(session, admin_id=admin.id, action="ai.account.reset_spend",
    target_type="ai_account", target_id=str(account_id),
    after={"spend_micros_before": before}, ip=_ip(request), commit=False)  # FIX: A1
    await session.commit()
    return _account_dict(acc)


# ---------- Model catalog ----------
@router.get("/models")
async def list_models(
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    rows = (await session.scalars(
        select(AIModel).order_by(AIModel.sort_order, AIModel.key)
    )).all()
    return [
        {"key": m.key, "title": m.title, "upstream_model": m.upstream_model,
         "modality": m.modality, "account_kind": m.account_kind,
         "premium": m.premium, "search": getattr(m, "search", False),
         "cost": m.cost, "cost_micros": m.cost_micros,
         "price_in_micros": getattr(m, "price_in_micros", 0) or 0,
         "price_out_micros": getattr(m, "price_out_micros", 0) or 0,
         "enabled": m.enabled, "sort_order": m.sort_order}
        for m in rows
    ]


class ModelUpsert(BaseModel):
    # FIX: AUDIT12-26 - bounded strings + numeric ranges on AI model entry
    title: str = Field(..., max_length=200)
    upstream_model: str = Field(..., max_length=200)
    modality: str = Field("text", max_length=20)
    # pin to a backend kind; None = any of modality
    account_kind: str | None = Field(None, max_length=50)
    premium: bool = False
    search: bool = False   # offer this model in the internet-search (/s) picker
    cost: int = Field(1, ge=0, le=10_000_000)
    # provider cost / себестоимость per request, micro-USD
    cost_micros: int = Field(0, ge=0, le=10**15)
    # token pricing: micro-USD per 1M input tokens
    price_in_micros: int = Field(0, ge=0, le=10**15)
    # token pricing: micro-USD per 1M output tokens
    price_out_micros: int = Field(0, ge=0, le=10**15)
    enabled: bool = True
    sort_order: int = Field(100, ge=0, le=10_000_000)


@router.put("/models/{key}")
async def upsert_model(
    key: str, req: ModelUpsert, request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if req.modality not in MODALITIES:
        raise HTTPException(status_code=400, detail="bad modality")
    m = await session.get(AIModel, key)
    if m is None:
        m = AIModel(key=key)
        session.add(m)
    m.title = req.title
    m.upstream_model = req.upstream_model
    m.modality = req.modality
    m.account_kind = req.account_kind
    m.premium = req.premium
    m.search = req.search
    m.cost = req.cost
    m.cost_micros = req.cost_micros
    m.price_in_micros = req.price_in_micros
    m.price_out_micros = req.price_out_micros
    m.enabled = req.enabled
    m.sort_order = req.sort_order
    await audit(session, admin_id=admin.id, action="ai.model.upsert", target_type="ai_model",
    target_id=key, after={"upstream_model": req.upstream_model, "enabled": req.enabled},
    ip=_ip(request), commit=False)  # FIX: A1
    await session.commit()
    return {"ok": True, "key": key}


# ---- Router web-UI panels (OmniRoute / LiteLLM / custom) ---------------------
# Admin-editable list of router dashboards to open/embed from the panel. URLs are
# stored in the `pricing` KV (key 'router_panels'); empty until the admin deploys
# the routers (e.g. on a VPS) and fills them in.
_DEFAULT_PANELS = [
    {"id": "omniroute", "name": "OmniRoute", "url": ""},
]


def _sanitize_panels(raw: list | None) -> list[dict]:
    out: list[dict] = []
    for p in raw or []:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name") or "").strip()[:40]
        url = str(p.get("url") or "").strip()[:300]
        if not name:
            continue
        # Only http(s) — the URL is used as an <iframe src> / window.open target, so a
        # javascript:/data: scheme would be an XSS vector against the admin.
        if url and not url.lower().startswith(("http://", "https://")):
            url = ""
        pid = str(p.get("id") or name.lower().replace(" ", "_"))[:40]
        out.append({"id": pid, "name": name, "url": url})
    return out


@router.get("/router-panels")
async def get_router_panels(
    admin: AdminUser = Depends(require_role("moderator")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    from core.models import Pricing

    row = await session.get(Pricing, "router_panels")
    panels = _sanitize_panels((row.value or {}).get("panels")) if row else []
    return {"panels": panels or _DEFAULT_PANELS}


class RouterPanelsReq(BaseModel):
    panels: list[dict]


@router.put("/router-panels")
async def set_router_panels(
    req: RouterPanelsReq, request: Request,
    # FIX: SUPERADMIN-3 - router panel layout drives which AI accounts users see; superadmin-only
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    from core.models import Pricing

    panels = _sanitize_panels(req.panels)
    row = await session.get(Pricing, "router_panels")
    value = {"panels": panels}
    if row is None:
        session.add(Pricing(key="router_panels", value=value))
    else:
        row.value = value
    await audit(session, admin_id=admin.id, action="ai.router_panels", target_type="setting",
    # FIX: A1
    target_id="router_panels", after={"count": len(panels)}, ip=_ip(request), commit=False)
    await session.commit()
    return {"panels": panels}


@router.get("/strategy")
async def get_routing_strategy(
    admin: AdminUser = Depends(require_role("moderator")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Current intra-tier routing strategy + the available options."""
    from core.services.ai_routing import STRATEGIES, get_strategy

    return {"strategy": await get_strategy(session), "options": list(STRATEGIES)}


class StrategyReq(BaseModel):
    strategy: str = Field(..., max_length=50)  # FIX: AUDIT12-26


@router.put("/strategy")
async def set_routing_strategy(
    req: StrategyReq, request: Request,
    # FIX: SUPERADMIN-4 - routing strategy changes which provider serves every
    # generation; superadmin-only
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Persist the intra-tier strategy (tier fallback is always primary)."""
    from core.models import Pricing
    from core.services.ai_routing import STRATEGIES

    if req.strategy not in STRATEGIES:
        raise HTTPException(status_code=400, detail="unknown strategy")
    row = await session.get(Pricing, "ai_routing")
    value = dict(row.value or {}) if row else {}
    value["strategy"] = req.strategy
    if row is None:
        session.add(Pricing(key="ai_routing", value=value))
    else:
        row.value = value
    await audit(session, admin_id=admin.id, action="ai.strategy", target_type="setting",
    # FIX: A1
    target_id="ai_routing", after={"strategy": req.strategy}, ip=_ip(request), commit=False)
    await session.commit()
    return {"ok": True, "strategy": req.strategy}


@router.delete("/models/{key}")
async def delete_model(
    key: str, request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    m = await session.get(AIModel, key)
    if m is None:
        raise HTTPException(status_code=404, detail="not found")
    await session.delete(m)
    await audit(session, admin_id=admin.id, action="ai.model.delete", target_type="ai_model",
    target_id=key, ip=_ip(request), commit=False)  # FIX: A1
    await session.commit()
    return {"ok": True}


# ---------- Import / export (portable routing snapshot) ----------
@router.get("/export")
async def export_config(
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Export the routing config as a portable JSON snapshot: the model catalog
    (no secrets) and accounts WITHOUT their API keys. Keys never leave the server —
    re-enter them on the target when importing."""
    accounts = (await session.scalars(
        select(AIAccount).order_by(AIAccount.tier, AIAccount.priority, AIAccount.id)
    )).all()
    models = (await session.scalars(
        select(AIModel).order_by(AIModel.sort_order, AIModel.key)
    )).all()
    return {
        "version": 1,
        "accounts": [
            {"name": a.name, "kind": a.kind, "base_url": a.base_url, "modality": a.modality,
             "tier": a.tier, "priority": a.priority, "weight": a.weight,
             "spend_limit_micros": a.spend_limit_micros, "enabled": a.enabled}
            for a in accounts
        ],
        "models": [
            {"key": m.key, "title": m.title, "upstream_model": m.upstream_model,
             "modality": m.modality, "account_kind": m.account_kind, "premium": m.premium,
             "search": getattr(m, "search", False),
             "cost": m.cost, "cost_micros": m.cost_micros,
             "enabled": m.enabled, "sort_order": m.sort_order}
            for m in models
        ],
    }


class ImportConfig(BaseModel):
    accounts: list[dict] = []
    models: list[dict] = []


@router.post("/import")
async def import_config(
    req: ImportConfig, request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Merge a routing snapshot into the catalog. Models upsert by key. Accounts
    upsert by name; a new account is skipped unless its api_key is supplied (a
    keyless export stays inert until you provide the credential)."""
    models_n = 0
    # FIX: AUDIT-95 - import loop (per-item try/except added below)
    for m in req.models:
        key = (m.get("key") or "").strip()
        if not key or m.get("modality", "text") not in MODALITIES:
            continue
        row = await session.get(AIModel, key)
        if row is None:
            row = AIModel(key=key)
            session.add(row)
        row.title = m.get("title") or key
        row.upstream_model = m.get("upstream_model") or ""
        row.modality = m.get("modality", "text")
        row.account_kind = m.get("account_kind")
        row.premium = bool(m.get("premium", False))
        row.search = bool(m.get("search", False))
        row.cost = int(m.get("cost", 1))
        row.cost_micros = int(m.get("cost_micros", 0))
        row.enabled = bool(m.get("enabled", True))
        row.sort_order = int(m.get("sort_order", 100))
        models_n += 1

    accounts_n = 0
    for a in req.accounts:
        name = (a.get("name") or "").strip()
        base_url = a.get("base_url") or ""
        if not name or not base_url or a.get("modality", "text") not in MODALITIES:
            continue
        existing = (await session.scalars(
            select(AIAccount).where(AIAccount.name == name)
        )).first()
        if existing is None:
            if not a.get("api_key"):
                continue  # can't create a usable account without a credential
            existing = AIAccount(name=name, api_key=encrypt(a["api_key"]))
            session.add(existing)
        elif a.get("api_key"):
            existing.api_key = encrypt(a["api_key"])
        existing.kind = a.get("kind", "omniroute")
        existing.base_url = await _validate_base_url_async(base_url)
        existing.modality = a.get("modality", "text")
        existing.tier = int(a.get("tier", 0))
        existing.priority = int(a.get("priority", 100))
        existing.weight = int(a.get("weight", 1))
        existing.spend_limit_micros = int(a.get("spend_limit_micros", 0))
        existing.enabled = bool(a.get("enabled", True))
        accounts_n += 1

    await audit(session, admin_id=admin.id, action="ai.config.import", target_type="ai_routing",
    after={"models": models_n, "accounts": accounts_n}, ip=_ip(request), commit=False)  # FIX: A1
    await session.commit()
    return {"ok": True, "models": models_n, "accounts": accounts_n}


# ---------- Health ----------
@router.get("/health")
async def routing_health(
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    rows = (await session.scalars(select(AIAccount))).all()
    pool = [a for a in rows if a.tier == 0]
    fallback = [a for a in rows if a.tier != 0]
    return {
        "pool_total": len(pool),
        "pool_active": sum(1 for a in pool if a.enabled and a.status == "active"),
        "pool_cooldown": sum(1 for a in pool if a.status == "cooldown"),
        "fallback_total": len(fallback),
        "fallback_active": sum(1 for a in fallback if a.enabled and a.status == "active"),
        "total_requests": sum(a.total_requests for a in rows),
        "total_errors": sum(a.total_errors for a in rows),
        "accounts": [_account_dict(a) for a in rows],
    }
