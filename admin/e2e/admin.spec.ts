/**
 * ADMIN journey (plan §6.4 / contract §9): login → dashboard → live map →
 * emergencies (filters + server CSV export) → users → junction overrides
 * (HOLD / REISSUE / FORCE_RELEASE with a reason) → logout.
 *
 * Runs against the demo backend (DEMO_MODE=1, seeded via
 * `python -m scripts.simulator --seed-only`, contract §8); the dev server is
 * started by playwright.config.ts with --mode demo (local proxy).
 */

import { expect, test } from "@playwright/test";
import { login, logout, runOverride } from "./helpers";

test.describe.configure({ mode: "serial" });

test("admin: dashboard shows live stats and recent alerts", async ({
  page,
}) => {
  await login(page, "admin");
  await expect(page.getByText("Active Emergencies")).toBeVisible();
  await expect(page.getByText("Pending Commands")).toBeVisible();
  await expect(page.getByText("Devices Online")).toBeVisible();
});

test("admin: live map renders sessions/junctions and freshness caption", async ({
  page,
}) => {
  await login(page, "admin");
  await page.getByRole("link", { name: "Live Map" }).click();
  await expect(page.getByText(/Last updated/)).toBeVisible();
  // The map container mounts (leaflet).
  await expect(page.locator(".leaflet-container").first()).toBeVisible();
});

test("admin: emergencies — filters, export, detail timeline", async ({
  page,
}) => {
  await login(page, "admin");
  await page.getByRole("link", { name: "Emergencies" }).click();

  // Contract §3 filter set for admins (status, dates, ambulance, junction,
  // hospital) — each server-side.
  await expect(page.getByLabel("Status")).toBeVisible();
  await expect(page.getByLabel("From date")).toBeVisible();
  await expect(page.getByLabel("To date")).toBeVisible();
  await expect(page.getByLabel("Ambulance")).toBeVisible();
  await expect(page.getByLabel("Junction")).toBeVisible();
  await expect(page.getByLabel("Hospital")).toBeVisible();

  // Apply a date-range filter (server round trip) — the toolbar shows counts.
  const today = new Date().toISOString().slice(0, 10);
  await page.getByLabel("From date").fill(today);
  await page.getByLabel("To date").fill(today);
  await expect(page.getByText(/of \d+|offset 0/)).toBeVisible();

  // Server CSV export (fetch + blob download, never a bare <a href>).
  const downloadPromise = page.waitForEvent("download", { timeout: 15_000 });
  await page.getByRole("button", { name: "Export CSV" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^emergencies.*\.csv$/);

  // Detail drawer renders the session timeline.
  const firstRow = page.locator(".table tbody tr").first();
  if (await firstRow.count()) {
    await firstRow.click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.getByText("Timeline")).toBeVisible();
    await page.keyboard.press("Escape");
  }
});

test("admin: users — search, filters and pagination controls", async ({
  page,
}) => {
  await login(page, "admin");
  await page.getByRole("link", { name: "Users" }).click();
  await expect(page.getByRole("button", { name: "New user" })).toBeVisible();
  await expect(page.getByLabel("Search email")).toBeVisible();
  // scope to the toolbar — the (closed) New-user drawer also has a Role select
  const toolbar = page.locator(".admin-toolbar");
  await expect(toolbar.getByLabel("Role")).toBeVisible();
  await expect(toolbar.getByLabel("Status")).toBeVisible();

  // Server-side search against the seeded demo accounts.
  await page.getByLabel("Search email").fill("hospital@demo.io");
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByRole("cell", { name: "hospital@demo.io" })).toBeVisible();
});

test("admin: junction override console (HOLD / REISSUE / FORCE_RELEASE with reason)", async ({
  page,
}) => {
  await login(page, "admin");
  await page.getByRole("link", { name: "Junctions" }).click();

  // Open the first junction's detail drawer.
  await page.locator(".table tbody tr").first().click();
  const drawer = page.getByRole("dialog");
  await expect(drawer).toBeVisible();

  // Reason is required: a short reason is rejected client-side.
  await drawer.getByLabel(/^Reason/).fill("abc");
  await drawer.getByRole("button", { name: "HOLD" }).click();
  await expect(drawer.getByText(/at least 5 characters/i)).toBeVisible();

  // Full actions with a valid reason — success or a truthful 409 conflict
  // (e.g. RELEASE_OUTSTANDING / NO_REISSUABLE_COMMAND) must surface inline.
  const reason = "e2e demo journey: verifying override console";
  await runOverride(page, "HOLD", reason);
  await runOverride(page, "REISSUE", reason);
  await runOverride(page, "FORCE_RELEASE", reason);
});

test("admin: logout returns to the login screen", async ({ page }) => {
  await login(page, "admin");
  await logout(page);
});
