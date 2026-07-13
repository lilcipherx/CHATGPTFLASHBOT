import { expect, Page, Route, test } from "@playwright/test";

// Admin auth e2e (Loop L6). Backend fully MOCKED via page.route so these run with no
// live API, deterministically. Covers the two boot outcomes App.tsx gates on:
// unauthenticated → the login card; a successful login → the admin shell.

// Every /api/admin/** call returns an empty object/array so a page that data-loads on
// mount (Dashboard) never reaches a real network and never 401s us back to login.
async function mockAdminApi(page: Page, loginRole = "superadmin") {
  await page.route("**/api/admin/**", (route: Route) => {
    const url = route.request().url();
    if (url.includes("/auth/login") && route.request().method() === "POST") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          access_token: "e2e-token",
          role: loginRole,
          mfa_setup_required: false,
        }),
      });
    }
    // Default: empty payload (shape-agnostic) — enough for the shell to render.
    return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
}

test("shows the login card when unauthenticated", async ({ page }) => {
  await mockAdminApi(page);
  await page.goto("/");

  await expect(page.locator("form.login-card")).toBeVisible();
  await expect(page.getByRole("button", { name: "Войти" })).toBeVisible();
  // The authenticated shell must NOT be present pre-login.
  await expect(page.locator("aside.sidebar")).toHaveCount(0);
});

test("logs in and renders the admin shell", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await mockAdminApi(page, "superadmin");
  await page.goto("/");

  await page.getByLabel("Email").fill("admin@example.com");
  await page.getByLabel("Пароль").fill("correct horse battery staple");
  await page.getByRole("button", { name: "Войти" }).click();

  // On success App swaps <Login> for <AdminShell> — the sidebar is the shell marker.
  await expect(page.locator("aside.sidebar")).toBeVisible();
  await expect(page.locator("form.login-card")).toHaveCount(0);
  expect(errors).toEqual([]);
});
