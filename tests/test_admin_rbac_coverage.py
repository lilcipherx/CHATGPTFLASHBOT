"""Zero-trust RBAC coverage guard (Loop L2 candidate C2).

Every mounted ``/api/admin/*`` route — except the two intentionally-public auth
endpoints — must resolve ``current_admin`` (or the 2FA-enrolling variant) somewhere
in its dependency tree. ``current_admin`` itself depends on ``ip_allowlisted``;
``require_role(...)`` depends on ``current_admin``. So this single introspection
asserts IP allow-list + JWT auth on every admin endpoint and fails loudly the day a
new endpoint forgets the dependency (the client-side ``RoleGuard`` in the SPA is UX
only — the backend dependency is the real gate).
"""
from __future__ import annotations

from fastapi.routing import APIRoute

from api.admin.deps import current_admin, current_admin_enrolling

# The only admin endpoints that legitimately run without an authenticated admin:
# login issues the session; refresh is validated by the refresh cookie/token itself.
_PUBLIC_ADMIN_ROUTES = {
    ("/api/admin/auth/login", "POST"),
    ("/api/admin/auth/refresh", "POST"),
}

_AUTH_GUARDS = {current_admin, current_admin_enrolling}


def _dependency_calls(dependant) -> set:
    """All callables reachable in a route's dependency tree (depth-first)."""
    seen: set = set()
    stack = list(dependant.dependencies)
    while stack:
        dep = stack.pop()
        if dep.call is not None:
            seen.add(dep.call)
        stack.extend(dep.dependencies)
    return seen


def test_every_admin_route_requires_admin() -> None:
    from api.main import app

    unguarded: list[tuple[str, list[str]]] = []
    checked = 0
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith("/api/admin/"):
            continue
        methods = route.methods or set()
        if any((route.path, m) in _PUBLIC_ADMIN_ROUTES for m in methods):
            continue
        checked += 1
        if not (_AUTH_GUARDS & _dependency_calls(route.dependant)):
            unguarded.append((route.path, sorted(methods)))

    assert checked > 20, f"expected many admin routes, introspected only {checked}"
    assert not unguarded, (
        f"admin routes missing current_admin/current_admin_enrolling dependency "
        f"(reachable without auth): {unguarded}"
    )
