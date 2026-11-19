/**
 * POLICE journey (plan §6.4 / contract §9): login → junction live (state,
 * override actions with a reason) → command log (attempt numbers + device
 * receipt wording) → device health. Serial within the file.
 */

import { expect, test } from "@playwright/test";
import { login, runOverride } from "./helpers";

test.describe.configure({ mode: "serial" });

test("police: junction live shows assigned junction and freshness", async ({
  page,
}) => {
  await login(page, "police");
  await page.getByRole("link", { name: "My Junctions" }).click();
  await expect(page.getByText(/Last updated/)).toBeVisible();
  // Junction state card renders online/offline and the signal state
  // ("Unknown" when the latest telemetry has no state — contract §5).
  await expect(page.getByText(/DEVICE ONLINE|DEVICE OFFLINE/)).toBeVisible();
});

test("police: override actions with a required reason", async ({ page }) => {
  await login(page, "police");
  await page.getByRole("link", { name: "My Junctions" }).click();

  await page.getByLabel(/^Reason/).fill("abc");
  await page.getByRole("button", { name: "Hold priority" }).click();
  await expect(page.getByText(/reason is required/i)).toBeVisible();

  const reason = "e2e demo journey: police override check";
  await runOverride(page, "HOLD", reason);
  await runOverride(page, "REISSUE", reason);
  await runOverride(page, "FORCE_RELEASE", reason);
});

test("police: command log shows attempts and device-receipt wording", async ({
  page,
}) => {
  await login(page, "police");
  await page.getByRole("link", { name: "Command Log" }).click();
  await expect(page.getByRole("columnheader", { name: "Attempt" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Device ack" })).toBeVisible();
  await expect(
    page.getByText(/acknowledged receipt of the command/i),
  ).toBeVisible();
});

test("police: device health cards render with telemetry drawers", async ({
  page,
}) => {
  await login(page, "police");
  await page.getByRole("link", { name: "Device Health" }).click();
  await expect(
    page.getByText(/DEVICE ONLINE|DEVICE OFFLINE|No devices registered/).first(),
  ).toBeVisible();
});

test("police: unauthorized deep link /emergencies redirects home", async ({
  page,
}) => {
  await login(page, "police");
  await page.goto("/emergencies");
  await expect(page.locator(".topbar")).toContainText("Dashboard");
});
