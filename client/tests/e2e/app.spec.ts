import { test, expect, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
const key = "ambulance-driver:v2";
const tab = (page: Page, name: string) =>
  page.getByRole("tab", { name: new RegExp(name) });
async function openLogin(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Skip", exact: true }).first().click();
  await expect(page.getByText("Driver Login", { exact: true })).toBeVisible();
}
async function signIn(page: Page) {
  await page
    .getByRole("textbox", { name: "Email" })
    .fill("driver001@example.com");
  await page.getByLabel("Password", { exact: true }).fill("123456");
  await page.getByRole("button", { name: "Login", exact: true }).click();
  await expect(page.getByText("Hi, Driver")).toBeVisible();
}
async function stored(page: Page) {
  return page.evaluate((k) => JSON.parse(localStorage.getItem(k) ?? "{}"), key);
}
async function screenshot(page: Page, name: string) {
  const directory = process.env.SCREENSHOT_DIR ?? "docs/screenshots";
  await mkdir(directory, { recursive: true });
  await page.screenshot({ path: `${directory}/${name}.png` });
}
test("onboarding, login validation, restore, and protected navigation", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Start Emergency", exact: true }),
  ).toBeVisible();
  await screenshot(page, "01-onboarding-emergency");
  await page.getByRole("button", { name: "Next", exact: true }).first().click();
  await expect(
    page.getByRole("heading", { name: "Stay on Route" }),
  ).toBeInViewport();
  await page.waitForTimeout(400);
  await screenshot(page, "02-onboarding-location");
  await page.getByRole("button", { name: "Next", exact: true }).nth(1).click();
  await expect(
    page.getByRole("heading", { name: "Faster Green Routes" }),
  ).toBeInViewport();
  await page.waitForTimeout(400);
  await screenshot(page, "03-onboarding-priority");
  await page.getByRole("button", { name: "Onboarding page 1" }).last().click();
  await expect(
    page.getByRole("heading", { name: "Start Emergency", exact: true }),
  ).toBeInViewport();
  await page.getByRole("button", { name: "Onboarding page 3" }).first().click();
  await page.getByRole("button", { name: "Get Started", exact: true }).click();
  await screenshot(page, "04-login");
  await expect
    .poll(async () => (await stored(page)).onboardingComplete)
    .toBe(true);
  await page.reload();
  await expect(page.getByText("Driver Login", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Login", exact: true }).click();
  await expect(
    page.getByText("Enter your email.", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "Email" })
    .fill("driver001@example.com");
  await page.getByLabel("Password", { exact: true }).fill("wrong");
  await page.getByRole("button", { name: "Show password" }).click();
  await expect(page.getByLabel("Password", { exact: true })).toHaveJSProperty(
    "type",
    "text",
  );
  await page.getByRole("button", { name: "Hide password" }).click();
  await page.getByRole("button", { name: "Login", exact: true }).click();
  await expect(page.getByText(/Incorrect driver email/)).toBeVisible();
  await signIn(page);
  // The signed-in identity is the backend user id — no mock driver id exists.
  await expect
    .poll(async () => (await stored(page)).auth?.driverId)
    .toBe("usr-driver-1");
  await screenshot(page, "05-home-idle");
  await page.reload();
  await expect(page.getByText("Hi, Driver")).toBeVisible();
  await tab(page, "Profile").click();
  await page.getByRole("button", { name: /Logout/ }).click();
  await expect(page.getByText("Driver Login", { exact: true })).toBeVisible();
  await expect.poll(async () => (await stored(page)).auth).toBeNull();
  await page.goto("/home");
  await expect(page.getByText("Driver Login", { exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});
test("emergency survives reload and completes into History", async ({
  page,
}) => {
  await openLogin(page);
  await signIn(page);
  await page
    .getByRole("button", { name: "START EMERGENCY", exact: true })
    .click();
  await expect(
    page.getByText("Tracking Active", { exact: true }),
  ).toBeVisible();
  await expect
    .poll(async () => (await stored(page)).active !== null, { timeout: 6000 })
    .toBe(true);
  const original = (await stored(page)).active.id;
  await page.reload();
  await expect(
    page.getByText("Tracking Active", { exact: true }),
  ).toBeVisible();
  expect((await stored(page)).active.id).toBe(original);
  await screenshot(page, "05-home-active");
  await tab(page, "History").click();
  await screenshot(page, "06-history");
  await tab(page, "Home").click();
  await page
    .getByRole("button", { name: "Stop Emergency", exact: true })
    .click();
  await expect(
    page.getByText("Tracking Standby", { exact: true }),
  ).toBeVisible();
  await expect.poll(async () => (await stored(page)).history.length).toBe(1);
  const saved = (await stored(page)).history[0];
  expect(saved.id).toBe(original);
  expect(saved.status).toBe("completed");
  expect(saved.events.at(-1).kind).toBe("ended");
  await tab(page, "History").click();
  await page
    .getByRole("button", { name: /Emergency session at/ })
    .first()
    .click();
  await expect(
    page.getByText("Emergency Ended", { exact: true }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Search history" }).click();
  await page.getByRole("textbox", { name: "Search hospitals" }).fill("unknown");
  await expect(page.getByText("No sessions found")).toBeVisible();
  await page
    .getByRole("textbox", { name: "Search hospitals" })
    .fill("City General");
  await expect(
    page.getByRole("button", { name: /Emergency session at/ }),
  ).toHaveCount(1);
});
test("profile edits and settings persist; active logout offers cancellation", async ({
  page,
}) => {
  await openLogin(page);
  await signIn(page);
  await tab(page, "Profile").click();
  await screenshot(page, "07-profile");
  await page
    .getByRole("button", { name: "Edit driver details", exact: true })
    .click();
  await page.getByRole("textbox", { name: "Full name" }).fill("Arjun Rao");
  await page.getByRole("button", { name: "Save Changes" }).click();
  await expect(page.getByText("Arjun Rao", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Edit ambulance details", exact: true })
    .click();
  await page
    .getByRole("textbox", { name: "Assigned hospital" })
    .fill("City General Hospital");
  await page.getByRole("button", { name: "Save Changes" }).click();
  await expect
    .poll(async () => (await stored(page)).ambulance.hospital)
    .toBe("City General Hospital");
  await page.getByRole("button", { name: /App Settings/ }).click();
  await page.getByRole("switch", { name: "Reduced motion" }).click();
  await page.getByRole("switch", { name: "Emergency confirmations" }).click();
  await page.getByRole("button", { name: "Close dialog" }).last().click();
  await page.reload();
  await expect(page.getByText("Arjun Rao", { exact: true })).toBeVisible();
  expect((await stored(page)).settings).toEqual({
    reducedMotion: true,
    confirmEmergency: true,
  });
  await tab(page, "Home").click();
  await page
    .getByRole("button", { name: "START EMERGENCY", exact: true })
    .click();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  expect((await stored(page)).active).toBeNull();
  await page
    .getByRole("button", { name: "START EMERGENCY", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Start Emergency", exact: true })
    .click();
  await tab(page, "Profile").click();
  await page.getByRole("button", { name: /Logout/ }).click();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  expect((await stored(page)).auth).not.toBeNull();
  await page.getByRole("button", { name: /Logout/ }).click();
  await page
    .getByRole("button", { name: "End Emergency & Logout", exact: true })
    .click();
  await expect(page.getByText("Driver Login", { exact: true })).toBeVisible();
  await expect.poll(async () => (await stored(page)).active).toBeNull();
});
test("compact viewport keeps login and navigation usable offline", async ({
  page,
  context,
}) => {
  await page.setViewportSize({ width: 320, height: 640 });
  await openLogin(page);
  await signIn(page);
  await context.setOffline(true);
  await page
    .getByRole("button", { name: "START EMERGENCY", exact: true })
    .click();
  await expect(
    page.getByText("Tracking Active", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Stop Emergency", exact: true })
    .click();
  await tab(page, "History").click();
  await expect(page.getByText("Past emergency sessions")).toBeVisible();
  await tab(page, "Profile").click();
  await expect(
    page.getByText("Driver Details", { exact: false }),
  ).toBeVisible();
  await screenshot(page, "08-compact-profile");
  await context.setOffline(false);
});

test("damaged storage offers explicit recovery", async ({ page }) => {
  await page.goto("/");
  await page.evaluate((k) => localStorage.setItem(k, "{invalid"), key);
  await page.reload();
  await expect(
    page.getByText("Your saved data could not be opened. Please retry."),
  ).toBeVisible();
  await page.getByRole("button", { name: "Reset Local Data" }).click();
  await expect(
    page.getByRole("heading", { name: "Start Emergency", exact: true }),
  ).toBeVisible();
  await expect.poll(async () => (await stored(page)).version).toBe(1);
});

test("short login viewport and larger text keep controls reachable", async ({
  page,
}) => {
  await openLogin(page);
  await page.setViewportSize({ width: 360, height: 420 });
  await signIn(page);
  await page.setViewportSize({ width: 393, height: 852 });
  await tab(page, "Profile").click();
  // Browser layout stress test; native Android font scaling still needs a device.
  await page.locator('[dir="auto"]').evaluateAll((elements) => {
    for (const element of elements) {
      if (!(element instanceof HTMLElement)) continue;
      const computed = getComputedStyle(element);
      element.style.fontSize = `${parseFloat(computed.fontSize) * 1.3}px`;
      element.style.lineHeight = `${parseFloat(computed.lineHeight) * 1.3}px`;
    }
  });
  await page
    .getByRole("button", { name: /App Settings/ })
    .scrollIntoViewIfNeeded();
  await screenshot(page, "09-profile-settings-large-text");
  await page.getByRole("button", { name: /App Settings/ }).click();
  await expect(
    page.getByRole("switch", { name: "Reduced motion" }),
  ).toBeVisible();
});
