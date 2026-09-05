/** Capture README screenshots from a running stack (API :8000, web :3000). Run: npx tsx scripts/screenshots.ts */
import { chromium } from "@playwright/test";
import path from "node:path";

const OUT = path.resolve(__dirname, "../../../docs/screenshots");
const BASE = process.env.BASE_URL ?? "http://localhost:3000";

async function main() {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, reducedMotion: "reduce" });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/`);
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${OUT}/01-landing-hero.png` });
  await page.goto(`${BASE}/demo`);
  await page.waitForURL(/\/app\/deals\//, { timeout: 90_000 });
  const base = page.url().replace(/\/?$/, "");
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT}/02-overview.png` });
  for (const [slug, file] of [["documents", "03-deal-room"], ["claims", "04-claim-audit"], ["financials", "05-financial-verification"], ["scenarios", "06-scenario-lab"], ["report", "07-report"], ["audit", "08-audit-history"]] as const) {
    await page.goto(`${base}/${slug}`);
    await page.waitForTimeout(900);
    await page.screenshot({ path: `${OUT}/${file}.png` });
  }
  // claim audit with the document viewer open (clickable cell citation)
  await page.goto(`${base}/claims`);
  await page.waitForTimeout(700);
  await page.getByRole("listbox", { name: "Claims" }).getByRole("option").first().click();
  await page.keyboard.press("e");
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${OUT}/09-citation-viewer.png` });
  await ctx.close();
  const mobile = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, reducedMotion: "reduce" });
  const mp = await mobile.newPage();
  await mp.goto(`${BASE}/`);
  await mp.waitForTimeout(600);
  await mp.screenshot({ path: `${OUT}/10-mobile-landing.png` });
  await mp.goto(`${base}/claims`);
  await mp.waitForTimeout(700);
  await mp.screenshot({ path: `${OUT}/11-mobile-claims.png` });
  await browser.close();
  console.log("screenshots written to", OUT);
}

main().catch((e) => { console.error(e); process.exit(1); });
