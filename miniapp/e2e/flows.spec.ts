import { expect, Page, Route, test } from "@playwright/test";

// Real end-to-end flows for the Mini App shell, driven against the built SPA (the
// Playwright webServer builds + previews it) with the backend fully MOCKED via
// page.route — so these run with no live API, deterministically, in CI. They cover the
// three load outcomes App.tsx gates on: authenticated render, the Telegram gate (401
// with no initData), and a graceful non-crashing error on a 503.

const PROFILE = {
  user_id: 1, username: "u", language_code: "en", credits: 42,
  is_premium: false, sub_expires: null,
};

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

// Route EVERY backend call. /profile gets `profileStatus` (200 with PROFILE, or an error
// status with an empty body); every other load call returns an empty list so nothing
// ever reaches a real network.
async function mockBackend(page: Page, profileStatus: number) {
  await page.route("**/api/**", (route) => {
    if (route.request().url().includes("/api/profile")) {
      return profileStatus === 200
        ? json(route, PROFILE)
        : route.fulfill({ status: profileStatus, contentType: "application/json", body: "{}" });
    }
    return json(route, []);
  });
}

test("renders the app shell when the backend authenticates", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await mockBackend(page, 200);
  await page.goto("/");

  // The bottom navigation renders only once the app is past the auth gate.
  await expect(page.locator("nav.nav")).toBeVisible();
  expect(errors).toEqual([]);
});

test("shows the Telegram gate when the backend refuses with 401", async ({ page }) => {
  await mockBackend(page, 401);
  await page.goto("/");

  // No Telegram initData + a 401 → the "open in Telegram" gate, NOT a wall of errors.
  await expect(page.locator(".gate")).toBeVisible();
  await expect(page.locator("nav.nav")).toHaveCount(0);
});

test("degrades gracefully (no crash) when profile load fails with 503", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await mockBackend(page, 503);
  await page.goto("/");

  // The SPA stays mounted and does not throw an uncaught error on a backend outage.
  await expect(page.locator("#root")).toBeAttached();
  expect(errors).toEqual([]);
});
