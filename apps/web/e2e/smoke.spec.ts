import { expect, test } from "@playwright/test";

test.describe("BearCase smoke", () => {
  test("landing page explains the workflow and links to the demo", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Check the seller's numbers");
    await expect(page.getByRole("link", { name: /Explore the demo/i }).first()).toBeVisible();
    await expect(page.getByText(/fictional/i).first()).toBeVisible();
  });

  test("demo opens the Northstar deal and the claim audit works by keyboard", async ({ page }) => {
    await page.goto("/demo");
    await expect(page).toHaveURL(/\/app\/deals\//, { timeout: 60_000 });
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Deal overview");
    await page.goto(page.url().replace(/\/?$/, "") + "/claims");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Claim Audit");
    const rows = page.getByRole("listbox", { name: "Claims" }).getByRole("option");
    await expect(rows.first()).toBeVisible();
    await expect(page.getByText("Contradicted").first()).toBeVisible();
    const isDesktop = (page.viewportSize()?.width ?? 0) >= 1024;
    const detailResponse = () => page.waitForResponse((r) => /\/api\/deals\/[^/]+\/claims\/[^/?]+$/.test(r.url()) && r.request().method() === "GET");
    if (isDesktop) {
      await rows.first().click();
      const loaded = detailResponse();
      await page.keyboard.press("j");
      await expect(page.getByRole("listbox", { name: "Claims" }).getByRole("option", { selected: true })).toBeAttached();
      await loaded;
      await page.keyboard.press("e");
    } else {
      const loaded = detailResponse();
      await rows.first().click();
      await loaded;
      await page.getByRole("button", { name: /Jump to source/ }).click();
    }
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });

  test("financials, scenarios, and report render with real values", async ({ page }) => {
    await page.goto("/demo");
    await expect(page).toHaveURL(/\/app\/deals\//, { timeout: 60_000 });
    const base = page.url().replace(/\/?$/, "");
    await page.goto(`${base}/financials`);
    await expect(page.getByText("$1,810,000").first()).toBeVisible();
    await page.goto(`${base}/scenarios`);
    await expect(page.getByRole("tab", { name: /Downside/ }).first()).toBeVisible();
    await page.goto(`${base}/report`);
    await expect(page.getByText(/material statements cited/)).toBeVisible();
    await expect(page.getByRole("link", { name: /PDF/ })).toBeVisible();
  });
});
