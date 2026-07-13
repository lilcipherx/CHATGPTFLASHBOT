import { defineConfig } from "@playwright/test";

// E2E for the Admin Panel. Builds + previews the SPA locally (port 4174 to avoid the
// Mini App's 4173); set E2E_BASE_URL to test a deployed instance instead. The backend
// is mocked per-test via page.route, so these run deterministically with no live API.
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:4174",
    headless: true,
    trace: "on-first-retry",
  },
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: "npm run build && npm run preview -- --port 4174",
        port: 4174,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
});
