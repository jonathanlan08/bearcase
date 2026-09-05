import { chromium } from "@playwright/test";
const b = await chromium.launch(); const p = await b.newPage();
const errs = []; p.on("console", (m) => { if (["error","warning"].includes(m.type())) errs.push(`[${m.type()}] ${m.text().slice(0,300)}`); }); p.on("pageerror", (e) => errs.push(`[pageerror] ${e.message.slice(0,300)}`));
await p.goto("http://localhost:3000/"); await p.waitForTimeout(2500);
await p.goto("http://localhost:3000/demo"); await p.waitForURL(/\/app\/deals\//, { timeout: 60000 }); await p.waitForTimeout(1500);
const base = p.url().replace(/\/?$/, "");
for (const s of ["claims","financials","scenarios","report"]) { await p.goto(`${base}/${s}`); await p.waitForTimeout(1200); }
console.log(errs.length ? errs.join("\n") : "no console errors"); await b.close();
