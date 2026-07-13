import { expect, Page, Route, test } from "@playwright/test";

// Responsive smoke (Loop L6): a Telegram Mini App renders inside narrow mobile
// webviews, so the authenticated shell must render — and NOT overflow horizontally —
// at small-phone and tablet widths. Backend fully mocked (same pattern as flows.spec)
// so this is deterministic and needs no live API.

const PROFILE = {
  user_id: 1, username: "u", language_code: "en", credits: 42,
  is_premium: false, sub_expires: null,
};

async function mockAuthedBackend(page: Page) {
  await page.route("**/api/**", (route: Route) => {
    const body = route.request().url().includes("/api/profile") ? PROFILE : [];
    return route.fulfill({
      status: 200, contentType: "application/json", body: JSON.stringify(body),
    });
  });
}

for (const { name, width, height } of [
  { name: "small phone (320x568)", width: 320, height: 568 },
  { name: "tablet (768x1024)", width: 768, height: 1024 },
]) {
  test(`authenticated shell fits ${name} without horizontal overflow`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));

    await page.setViewportSize({ width, height });
    await mockAuthedBackend(page);
    await page.goto("/");

    await expect(page.locator("nav.nav")).toBeVisible();
    expect(errors).toEqual([]);

    // No horizontal scroll: the document must not be wider than the viewport (a common
    // Mini App bug — a fixed-width element pushing the layout past the webview edge).
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(scrollWidth).toBeLessThanOrEqual(width + 1);
  });
}
