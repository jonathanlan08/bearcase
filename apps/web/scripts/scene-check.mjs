import { chromium } from "@playwright/test";
const b = await chromium.launch({ args: ["--enable-webgl", "--ignore-gpu-blocklist", "--use-angle=swiftshader"] });
const p = await b.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
await p.goto("http://localhost:3000/", { waitUntil: "networkidle" });
await p.waitForTimeout(2500);
const info = await p.evaluate(() => ({ canvas: !!document.querySelector("canvas"), webgl: !!document.createElement("canvas").getContext("webgl2") }));
console.log(info);
const total = await p.evaluate(() => { const el = document.querySelector("main > div"); return el.offsetHeight - window.innerHeight; });
for (const pr of [0, 0.25, 0.45, 0.58, 0.75, 0.86, 0.98]) {
  await p.evaluate((y) => window.scrollTo(0, y), Math.round(pr * total));
  await p.waitForTimeout(1600);
  await p.screenshot({ path: `/tmp/scene-${String(pr).replace(".", "_")}.png` });
}
await b.close();
console.log("done", total);
