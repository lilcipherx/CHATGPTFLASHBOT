import { defineConfig } from "@playwright/test";

// E2E smoke for the Mini App. By default it builds + previews the SPA locally;
// set E2E_BASE_URL to test a deployed staging instead.
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:4173",
    headless: true,
    trace: "on-first-retry",
  },
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: "npm run build && npm run preview -- --port 4173",
        port: 4173,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
});
