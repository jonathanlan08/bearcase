import { chromium } from "@playwright/test";
const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, reducedMotion: "reduce" }); const p = await ctx.newPage();
await p.goto("http://localhost:3000/demo"); await p.waitForURL(/\/app\/deals\//, { timeout: 90000 });
await p.goto(p.url().replace(/\/?$/, "") + "/financials"); await p.waitForTimeout(800);
await p.getByRole("button", { name: /Ask the Deal/ }).click();
await p.getByRole("button", { name: "Why was adjusted EBITDA reduced?" }).click();
await p.waitForTimeout(2500);
await p.screenshot({ path: "/Users/jonathanlan/bearcase/docs/screenshots/12-ask-the-deal.png" });
await b.close(); console.log("ok");
