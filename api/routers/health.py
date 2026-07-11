from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.deps import require_role  # FIX: F21 - RBAC for /health/providers
from core.config import settings
from core.db import get_session
from core.models import AdminUser, GenerationJob, User

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness — the process is up. Cheap, no dependencies (safe for k8s liveness)."""
    return {"status": "ok", "env": settings.env, "brand": settings.brand_name}


@router.get("/health/ready")
async def readiness(session: AsyncSession = Depends(get_session)) -> Response:
    """Readiness — DB + Redis reachable. Returns 503 if a dependency is down so an
    orchestrator (k8s/compose healthcheck, Caddy) stops routing traffic here."""
    import json as _json

    checks = {"database": False, "redis": False}
    try:
        await session.scalar(select(1))
        checks["database"] = True
    except Exception:  # noqa: BLE001 — report, don't crash the probe
        pass
    try:
        from core.redis_client import redis_client

        await redis_client.ping()
        checks["redis"] = True
    except Exception:  # noqa: BLE001
        pass
    ok = all(checks.values())
    return Response(
        content=_json.dumps({"status": "ok" if ok else "degraded", "checks": checks}),
        media_type="application/json",
        status_code=200 if ok else 503,
    )


@router.get("/health/providers")
async def providers_health(
    admin: AdminUser = Depends(require_role("admin")),
) -> dict:
    """Which AI/payment backends are configured + available. NO secrets returned —
    only booleans. FIX: F21 - gated behind admin RBAC: this endpoint enumerates which
    provider keys are configured — a free reconnaissance tool for an attacker deciding
    which provider accounts to target. Internal monitoring uses /metrics with a token
    instead, so there is no operational reason to leave this public."""
    from core.payments import get_provider
    # require_role is imported above; admin dependency enforces it.

    ai = {
        "openai": bool(settings.openai_api_key),
        "anthropic": bool(settings.anthropic_api_key),
        "google": bool(settings.google_api_key),
        "openrouter": bool(settings.openrouter_api_key),
        "deepseek": bool(settings.deepseek_api_key),
        "perplexity": bool(settings.perplexity_api_key),
    }
    pay = {
        name: (p.is_available() if (p := get_provider(name)) else False)
        for name in ("yookassa", "stripe", "sbp_tribute", "crypto")
    }
    return {
        "ai_configured": ai,
        "ai_any": any(ai.values()),
        "payments_available": pay,
    }


@router.get("/metrics")
async def metrics(
    token: str = "",
    x_metrics_token: str = Header(default=""),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Minimal Prometheus exposition — scrape target for Grafana dashboards.

    When METRICS_TOKEN is configured, the scraper must present it (query ?token=
    or X-Metrics-Token header) so user counts aren't world-readable.

    FIX: F22 / AUDIT-A2 - the token is REQUIRED on any non-local deploy, not only when
    is_public_deploy is True. is_public_deploy is inferred from PUBLIC_DEPLOY or a
    WEBHOOK_BASE_URL, so a prod bot running in POLLING mode (no webhook URL) evaluated
    to False and silently served total/premium/banned user counts + job stats
    unauthenticated. Fail closed (403) unless this is clearly a local dev/test box."""
    if not settings.metrics_token:
        if settings.is_public_deploy or settings.env not in ("dev", "test"):
            raise HTTPException(
                status_code=403,
                detail="METRICS_TOKEN must be set outside local dev/test "
                       "(configure it for the scraper)",
            )
        # Local dev/test only: keep the historical permissive behaviour.
    else:
        provided = token or x_metrics_token
        if not hmac.compare_digest(provided, settings.metrics_token):
            raise HTTPException(status_code=403, detail="forbidden")
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    users = await session.scalar(select(func.count()).select_from(User)) or 0
    premium = await session.scalar(
        select(func.count()).select_from(User).where(User.sub_expires > now)
    ) or 0
    banned = await session.scalar(
        select(func.count()).select_from(User).where(User.is_banned.is_(True))
    ) or 0
    pending = await session.scalar(
        select(func.count()).select_from(GenerationJob)
        .where(GenerationJob.status.in_(("pending", "processing")))
    ) or 0
    failed = await session.scalar(
        select(func.count()).select_from(GenerationJob)
        .where(GenerationJob.status == "failed")
    ) or 0
    body = (
        "# HELP aibot_users_total Total users\n"
        "# TYPE aibot_users_total gauge\n"
        f"aibot_users_total {users}\n"
        "# HELP aibot_users_premium Active premium subscriptions\n"
        "# TYPE aibot_users_premium gauge\n"
        f"aibot_users_premium {premium}\n"
        "# HELP aibot_users_banned Banned users\n"
        "# TYPE aibot_users_banned gauge\n"
        f"aibot_users_banned {banned}\n"
        "# HELP aibot_jobs_pending Pending/processing generation jobs\n"
        "# TYPE aibot_jobs_pending gauge\n"
        f"aibot_jobs_pending {pending}\n"
        "# HELP aibot_jobs_failed Failed generation jobs (lifetime)\n"
        "# TYPE aibot_jobs_failed counter\n"
        f"aibot_jobs_failed {failed}\n"
    )
    return Response(content=body, media_type="text/plain")
