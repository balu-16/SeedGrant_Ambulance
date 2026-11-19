import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright e2e (plan §6.4 / contract §9).
 *
 * The tests run against the DEMO backend (contract §8): the webServer starts
 * `vite dev --mode demo`, which loads `.env.demo` (VITE_API_URL=/api/v1 — the
 * dev proxy → http://localhost:8000, NOT the Render URL pinned in
 * .env.local). The backend must be running with DEMO_MODE=1 and seeded via
 * `python -m scripts.simulator --seed-only` (server/) before the journeys run.
 *
 * Chromium only, no retries: failures are investigated, not flake-polished.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: 0,
  workers: 1,
  timeout: 60_000,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:5173",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "npm run dev -- --mode demo",
    url: "http://localhost:5173",
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
