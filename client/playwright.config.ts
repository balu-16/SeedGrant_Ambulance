import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: "http://localhost:8081",
    viewport: { width: 393, height: 852 },
    launchOptions: { args: ["--no-sandbox"] },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      // Hermetic backend: the app runs in fully real mode against this mock
      // (no demo path exists in app code anymore).
      command: "node tests/mock-backend.mjs",
      url: "http://localhost:8787/healthz",
      reuseExistingServer: true,
      timeout: 30_000,
    },
    {
      command: "npm run web -- --port 8081",
      url: "http://localhost:8081",
      reuseExistingServer: true,
      timeout: 120000,
      env: {
        // Do not let a developer's local .env (or a deployed Render URL)
        // override the hermetic mock used by these tests.
        EXPO_NO_DOTENV: "1",
        EXPO_PUBLIC_API_URL: "http://127.0.0.1:8787",
      },
    },
  ],
});
