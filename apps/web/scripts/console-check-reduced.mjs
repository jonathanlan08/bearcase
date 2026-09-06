import { chromium } from "@playwright/test";
const b = await chromium.launch(); const ctx = await b.newContext({ reducedMotion: "reduce", viewport: { width: 1440, height: 900 } }); const p = await ctx.newPage();
const errs = []; p.on("console", (m) => { if (["error","warning"].includes(m.type())) errs.push(`[${m.type()}] ${m.text().slice(0,400)}`); }); p.on("pageerror", (e) => errs.push(`[pageerror] ${e.message.slice(0,400)}`));
await p.goto("http://localhost:3000/", { waitUntil: "networkidle" }); await p.waitForTimeout(2000);
await p.evaluate(() => window.scrollTo(0, document.body.scrollHeight * 0.4)); await p.waitForTimeout(1500);
const badge = await p.locator("nextjs-portal").count();
console.log("errors:", errs.length ? errs.join("\n") : "none", "| nextjs-portal elements:", badge);
await b.close();
