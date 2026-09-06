import { chromium } from "@playwright/test";
const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, reducedMotion: "reduce" });
await p.goto("http://localhost:3000/", { waitUntil: "networkidle" });
const sections = await p.$$("main > section");
for (const [i, s] of sections.entries()) { await s.scrollIntoViewIfNeeded(); await p.waitForTimeout(400); await s.screenshot({ path: `/tmp/section-${i + 1}.png` }); }
await p.goto("http://localhost:3000/demo"); await p.waitForURL(/\/app\/deals\//, { timeout: 90000 });
await p.goto(p.url().replace(/\/?$/, "") + "/financials"); await p.waitForTimeout(900);
const fig = await p.$("figure"); await fig.screenshot({ path: "/tmp/app-waterfall.png" });
await b.close(); console.log("sections", sections.length);
