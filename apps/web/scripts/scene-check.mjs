/* Visual check for the Evidence Core hero against a running dev server (default http://localhost:3000).
 *
 *   node scripts/scene-check.mjs                 # desktop 1440×900
 *   SCENE_VIEWPORT=390x844 node scripts/scene-check.mjs
 *   SCENE_URL=http://localhost:3001 SCENE_OUT=/path/to/dir node scripts/scene-check.mjs
 *
 * Scrolls the hero to the middle of each of the three chapters (plus the extremes), prints the active caption at each stop,
 * saves a screenshot per stop, then toggles the pause control and reports whether the canvas went away and came back.
 * Uses SwiftShader so it runs on machines without a GPU; exits 1 if a caption or the pause control is missing. */
import { chromium } from "@playwright/test";

const url = process.env.SCENE_URL ?? "http://localhost:3000/";
const out = process.env.SCENE_OUT ?? "/tmp";
const [w, h] = (process.env.SCENE_VIEWPORT ?? "1440x900").split("x").map((n) => Number(n));

const b = await chromium.launch({ args: ["--enable-webgl", "--ignore-gpu-blocklist", "--use-angle=swiftshader"] });
const p = await b.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
await p.addInitScript(() => { try { localStorage.removeItem("bc.scene.paused"); } catch {} });
await p.goto(url, { waitUntil: "networkidle" });
await p.waitForTimeout(2500);

const info = await p.evaluate(() => ({ canvas: !!document.querySelector("canvas"), webgl: !!document.createElement("canvas").getContext("webgl2") }));
console.log(info);
const total = await p.evaluate(() => { const el = document.querySelector("main > div"); return el.offsetHeight - window.innerHeight; });
console.log("scroll range", total, "px for", w + "x" + h);

let ok = true;
const stops = [0, 1 / 6, 1 / 3 + 0.01, 0.5, 2 / 3 + 0.01, 5 / 6, 0.999];
for (const s of stops) {
  await p.evaluate((y) => window.scrollTo(0, y), Math.round(s * total));
  await p.waitForTimeout(1600);
  const caption = await p.evaluate(() => document.querySelector('[aria-current="step"]')?.textContent?.trim() ?? null);
  if (!caption) ok = false;
  const file = `${out}/scene-${s.toFixed(2).replace(".", "_")}.png`;
  await p.screenshot({ path: file });
  console.log(`s=${s.toFixed(2)}  ${caption ?? "(no active caption)"}  → ${file}`);
}

await p.evaluate(() => window.scrollTo(0, 0));
await p.waitForTimeout(600);
const pause = p.getByRole("button", { name: /Pause 3D/ });
if (await pause.count()) {
  await pause.click();
  await p.waitForTimeout(400);
  const paused = await p.evaluate(() => ({ canvas: !!document.querySelector("canvas"), pressed: document.querySelector('button[aria-pressed="true"]')?.textContent?.trim() ?? null, stored: localStorage.getItem("bc.scene.paused") }));
  console.log("after pause", paused);
  if (paused.canvas || paused.pressed !== "Resume 3D" || paused.stored !== "1") ok = false;
  await p.screenshot({ path: `${out}/scene-paused.png` });
  await p.getByRole("button", { name: /Resume 3D/ }).click();
  await p.waitForTimeout(2500);
  const resumed = await p.evaluate(() => ({ canvas: !!document.querySelector("canvas"), stored: localStorage.getItem("bc.scene.paused") }));
  console.log("after resume", resumed);
  if (!resumed.canvas || resumed.stored !== "0") ok = false;
} else {
  console.log("no pause control rendered (WebGL unavailable or reduced motion); static composition only");
  ok = ok && !info.webgl;
}

await b.close();
console.log(ok ? "scene-check: ok" : "scene-check: FAILED");
process.exit(ok ? 0 : 1);
