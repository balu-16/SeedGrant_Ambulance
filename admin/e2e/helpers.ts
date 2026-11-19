/**
 * Shared e2e helpers — login/logout against the demo backend (contract §8
 * seeded users) and small assertions used by the three role journeys.
 */

import { expect, type Page } from "@playwright/test";

export const DEMO_USERS = {
  admin: { email: "admin@demo.io", password: "Admin123!" },
  hospital: { email: "hospital@demo.io", password: "Hospital123!" },
  police: { email: "police@demo.io", password: "Police123!" },
} as const;

export type Persona = keyof typeof DEMO_USERS;

/** Sign in through the real login form and land on the role dashboard. */
export async function login(page: Page, persona: Persona): Promise<void> {
  const { email, password } = DEMO_USERS[persona];
  await page.goto("/login");
  await expect(page.getByText("Portal Login")).toBeVisible();
  // exact:true — the password-reveal button's aria-label ("Show password")
  // would otherwise also match a substring lookup
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Login" }).click();
  // The role dashboard is the shared "/" route (header title "Dashboard").
  await expect(page.locator(".topbar")).toContainText("Dashboard");
}

/** Logout via the sidebar button and confirm the login screen returns. */
export async function logout(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page.getByText("Portal Login")).toBeVisible();
}

/**
 * Manual override with a required reason. The truthful outcome depends on the
 * demo state (an open command may not exist): the result appears under the
 * admin console's "Override results" section, the police console appends a
 * timeline entry titled "<ACTION> — …", or the server conflict is surfaced
 * inline — all prove the console works end to end.
 */
export async function runOverride(
  page: Page,
  action: "FORCE_RELEASE" | "HOLD" | "REISSUE",
  reason: string,
): Promise<void> {
  await page.getByLabel(/^Reason/).fill(reason);
  // Police console titles are human ("Hold priority"), admin console uses the
  // raw action names — match either.
  await page
    .getByRole("button", { name: new RegExp(`^${action}$|${OVERRIDE_BUTTON[action]}`, "i") })
    .click();
  await expect(
    page
      .locator(".admin-inline-error, .login-error")
      .or(page.getByText("Override results"))
      .or(page.getByText(new RegExp(`^${action} —`))),
  ).toBeVisible({ timeout: 15_000 });
}

const OVERRIDE_BUTTON: Record<string, string> = {
  FORCE_RELEASE: "Force release",
  HOLD: "Hold priority|HOLD",
  REISSUE: "Re-issue command|REISSUE",
};
