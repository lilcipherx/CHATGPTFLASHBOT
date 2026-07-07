import { expect, test } from "@playwright/test";

// Smoke: the SPA shell must mount without a hard crash, even outside Telegram
// (the app guards WebApp access). This catches build/runtime breakage in CI.
test("app shell mounts", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(page.locator("#root")).toBeAttached();
  // No uncaught fatal errors on load.
  expect(errors).toEqual([]);
});
