"""Aggregate admin sub-routers under /admin (RBAC-protected, IP allow-list)."""
from fastapi import APIRouter

from api.admin import (
    admins,
    ai_routing,
    analytics,
    attention,
    auth,
    banners,
    bots,
    business,
    channel,
    contests,
    cron,
    crm,
    effects,
    exports,
    feedback,
    gallery,
    health,
    localization,
    maintenance,
    messaging,
    ops,
    router_containers,
    traffic,
    users,
)

admin_router = APIRouter(prefix="/admin")
admin_router.include_router(auth.router)
admin_router.include_router(users.router)
admin_router.include_router(ops.router)
admin_router.include_router(ai_routing.router)
admin_router.include_router(effects.router)
admin_router.include_router(banners.router)
admin_router.include_router(business.router)
admin_router.include_router(feedback.router)
admin_router.include_router(crm.router)
admin_router.include_router(exports.router)
admin_router.include_router(messaging.router)
admin_router.include_router(health.router)
admin_router.include_router(gallery.router)
admin_router.include_router(traffic.router)
admin_router.include_router(analytics.router)
admin_router.include_router(admins.router)
admin_router.include_router(localization.router)
admin_router.include_router(contests.router)
admin_router.include_router(channel.router)
admin_router.include_router(attention.router)
admin_router.include_router(bots.router)
admin_router.include_router(maintenance.router)
admin_router.include_router(router_containers.router)
admin_router.include_router(cron.router)
