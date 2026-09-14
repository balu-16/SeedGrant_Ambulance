import { test, expect } from "@playwright/test";
test("debug login", async ({ page }) => {
  const logs: string[] = [];
  page.on("console", (m) => logs.push(`console: ${m.text().slice(0, 200)}`));
  page.on("request", (r) => {
    if (!r.url().includes("8081")) logs.push(`REQ: ${r.method()} ${r.url()}`);
  });
  page.on("requestfailed", (r) =>
    logs.push(`FAILED: ${r.method()} ${r.url()} :: ${r.failure()?.errorText}`),
  );
  page.on("response", (r) => {
    if (!r.url().includes("8081")) logs.push(`RESP: ${r.status()} ${r.url()}`);
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Skip", exact: true }).first().click();
  await page
    .getByRole("textbox", { name: "Driver ID / Email" })
    .fill("driver001@example.com");
  await page.getByLabel("Password", { exact: true }).fill("wrong");
  await page.getByRole("button", { name: "Login", exact: true }).click();
  await page.waitForTimeout(4000);
  const bodyText = await page.locator("body").innerText();
  console.log("=== LOGS ===\n" + logs.join("\n"));
  console.log(
    "=== BODY (last 400) ===\n" + bodyText.slice(-400).replace(/\n+/g, " | "),
  );
});
