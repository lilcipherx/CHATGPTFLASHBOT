import { expect, Page, Route, test } from "@playwright/test";

// Admin RBAC e2e (Loop L6) — the critical admin security-UX flow: the sidebar must
// hide routes above the signed-in admin's role (the SUPERADMIN-12 filter, mirroring
// RoleGuard). This is UX defence-in-depth; the backend require_role is authoritative
// (guarded by tests/test_admin_rbac_coverage.py), but a leaking sidebar would still
// expose privileged surface area. Backend mocked; role seeded via localStorage.

async function bootAs(page: Page, role: string) {
  // Seed the non-sensitive auth flags BEFORE the app boots so isAuthed() is true with
  // the given role (mirrors what api.ts:login writes) — no login round-trip needed.
  await page.addInitScript((r) => {
    localStorage.setItem("admin_authed", "1");
    localStorage.setItem("admin_role", r as string);
    localStorage.setItem("admin_email", "e2e@example.com");
  }, role);
  // Any data-load returns empty so the shell renders without a 401 bounce.
  await page.route("**/api/admin/**", (route: Route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "{}" }),
  );
  await page.goto("/");
  await expect(page.locator("aside.sidebar")).toBeVisible();
}

const SUPERADMIN_ONLY = ["Цены", "AI-роутинг", "Функции", "Админы", "Обслуживание", "Безопасность"];
const SUPPORT_VISIBLE = ["Дашборд", "Пользователи", "Платежи", "Аудит-лог"];

// Sidebar entries are NavLinks (role=link). Their accessible name includes the
// material-symbols icon ligature (e.g. "group Пользователи"), so match by role+name
// substring rather than exact text.
const navLink = (page: Page, label: string) =>
  page.locator("aside.sidebar").getByRole("link", { name: label });

test("support role hides superadmin + moderator routes in the sidebar", async ({ page }) => {
  await bootAs(page, "support");

  for (const label of SUPPORT_VISIBLE) {
    await expect(navLink(page, label)).toBeVisible();
  }
  for (const label of SUPERADMIN_ONLY) {
    await expect(navLink(page, label)).toHaveCount(0);
  }
  // "Аналитика" is moderator-min → also hidden from support.
  await expect(navLink(page, "Аналитика")).toHaveCount(0);
});

test("superadmin role sees the superadmin routes", async ({ page }) => {
  await bootAs(page, "superadmin");

  for (const label of [...SUPPORT_VISIBLE, ...SUPERADMIN_ONLY, "Аналитика"]) {
    await expect(navLink(page, label)).toBeVisible();
  }
});
