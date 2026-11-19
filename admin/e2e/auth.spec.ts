/**
 * Auth journey (contract §1/§9): driver accounts are rejected, bad creds show
 * the server error, and a signed-in session survives a reload through the
 * cookie refresh (memory-only access token).
 */

import { expect, test } from "@playwright/test";
import { DEMO_USERS, login } from "./helpers";

test.describe.configure({ mode: "serial" });

test("driver accounts are rejected by the portal", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill("driver@demo.io");
  await page.getByLabel("Password", { exact: true }).fill("Demo123!");
  await page.getByRole("button", { name: "Login" }).click();
  // Server 403 DRIVER_ROLE_NOT_ALLOWED (client guard also active).
  await expect(
    page
      .getByText(/driver accounts use the mobile app/i)
      .or(page.locator(".login-error").filter({ hasText: /driver|not allowed/i })),
  ).toBeVisible();
  await expect(page.getByText("Portal Login")).toBeVisible();
});

test("invalid credentials surface the server error inline", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill("admin@demo.io");
  await page.getByLabel("Password", { exact: true }).fill("wrong-password");
  await page.getByRole("button", { name: "Login" }).click();
  await expect(page.locator(".login-error")).toBeVisible();
});

test("admin session persists across reload (no localStorage tokens)", async ({
  page,
}) => {
  await login(page, "admin");
  // Contract §1/§9: access token lives in memory only — nothing in localStorage.
  const stored = await page.evaluate(() =>
    localStorage.getItem("admin-portal:tokens:v1"),
  );
  expect(stored).toBeNull();

  await page.reload();
  await expect(page.locator(".topbar")).toContainText("Dashboard");
  await expect(page.getByText(DEMO_USERS.admin.email)).toBeVisible();
});
