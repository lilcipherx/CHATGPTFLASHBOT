# Admin panel (Phase 6.5)

React + TS + Vite SPA for product management (§11A of the plan). Reuses the Mini
App stack and talks to a dedicated, RBAC-protected `api/admin/` router (JWT +
TOTP 2FA, IP allow-list).

Data models are already defined (`core/models/admin.py`:
`AdminUser`, `AdminAuditLog`; plus `Broadcast`, `PromoCode`, `Pricing`). The
admin API router and React pages (Dashboard, Users, Payments, Pricing, Catalogs,
Gate-channels, Referrals, Providers, Moderation, Audit) are built in Phase 6.5.

Scaffold the app the same way as `miniapp/` when starting that phase.
