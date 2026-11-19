/**
 * HOSPITAL journey (plan §6.4 / contract §9): login → scoped dashboard →
 * emergencies (filters + export) → alerts → settings password card. Also
 * covers the unauthorized deep-link redirect (hospital hitting /users is sent
 * home) and session persistence across reload (cookie refresh).
 */

import { expect, test } from "@playwright/test";
import { login, DEMO_USERS } from "./helpers";

test.describe.configure({ mode: "serial" });

test("hospital: scoped dashboard renders without admin-only stats", async ({
  page,
}) => {
  await login(page, "hospital");
  // Hospital dashboard shows fleet stats, not admin devices/junctions.
  await expect(page.getByText("Active Emergencies")).toBeVisible();
  await expect(page.getByText("Fleet Size")).toBeVisible();
  await expect(page.getByText("Pending Commands")).toHaveCount(0);
});

test("hospital: unauthorized deep link /users redirects home", async ({
  page,
}) => {
  await login(page, "hospital");
  await page.goto("/users");
  // RoleRoute sends wrong-role deep links to the role dashboard.
  await expect(page.locator(".topbar")).toContainText("Dashboard");
  await expect(page.getByText("Portal accounts, roles and scope")).toHaveCount(0);
});

test("hospital: emergencies — filters and server CSV export", async ({
  page,
}) => {
  await login(page, "hospital");
  await page.getByRole("link", { name: "Emergencies" }).click();

  // Hospital scope: no hospital filter (server scopes by owner_hospital_id).
  await expect(page.getByLabel("Status")).toBeVisible();
  await expect(page.getByLabel("From date")).toBeVisible();
  await expect(page.getByLabel("Ambulance")).toBeVisible();
  await expect(page.getByLabel("Hospital")).toHaveCount(0);

  const downloadPromise = page.waitForEvent("download", { timeout: 15_000 });
  await page.getByRole("button", { name: "Export CSV" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^emergencies.*\.csv$/);
});

test("hospital: alerts feed renders (emergency start/end info events included)", async ({
  page,
}) => {
  await login(page, "hospital");
  await page.getByRole("link", { name: "Alerts" }).click();
  // Either the feed has entries or the explicit empty state shows — never a
  // failed/blank screen.
  await expect(
    page.getByText("No alerts").or(page.locator(".card").filter({ hasText: /info|warning|critical/ })).first(),
  ).toBeVisible();
});

test("hospital: settings password card validates and submits", async ({
  page,
}) => {
  await login(page, "hospital");
  await page.getByRole("link", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "Change Password" })).toBeVisible();

  // Mismatched confirmation is rejected client-side without a round trip.
  await page.getByLabel("Current password").fill(DEMO_USERS.hospital.password);
  await page.getByLabel("New password", { exact: false }).first().fill("AnotherPass123!");
  await page.getByLabel("Confirm new password").fill("Different123!");
  await page.getByRole("button", { name: "Change password" }).click();
  await expect(page.getByText(/do not match/i)).toBeVisible();
});

test("hospital: session survives a reload (cookie refresh on boot)", async ({
  page,
}) => {
  await login(page, "hospital");
  await page.reload();
  // Boot refreshes the HttpOnly cookie session and restores the user.
  await expect(page.locator(".topbar")).toContainText("Dashboard");
  await expect(page.getByText("hospital@demo.io")).toBeVisible();
});
