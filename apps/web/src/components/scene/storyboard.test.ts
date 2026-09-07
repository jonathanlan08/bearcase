import { describe, expect, it } from "vitest";
import { CHAPTERS, STAGES, chapterIndex, createSceneStore, statusReveal, storyProgress } from "./storyboard";

describe("storyboard", () => {
  it("gives each chapter one third of the scroll and maps onto its storyboard span", () => {
    expect(storyProgress(0)).toBe(0);
    expect(storyProgress(1)).toBe(1);
    expect(storyProgress(1 / 3)).toBeCloseTo(CHAPTERS[1].p, 10);
    expect(storyProgress(2 / 3)).toBeCloseTo(CHAPTERS[2].p, 10);
    expect(chapterIndex(0)).toBe(0);
    expect(chapterIndex(0.33)).toBe(0);
    expect(chapterIndex(0.34)).toBe(1);
    expect(chapterIndex(0.67)).toBe(2);
    expect(chapterIndex(1)).toBe(2);
    expect(chapterIndex(-1)).toBe(0);
    expect(chapterIndex(2)).toBe(2);
  });

  it("is continuous and monotonic across chapter boundaries", () => {
    let prev = 0;
    for (let k = 0; k <= 300; k++) {
      const p = storyProgress(k / 300);
      expect(p).toBeGreaterThanOrEqual(prev);
      expect(p - prev).toBeLessThan(0.02);
      prev = p;
    }
  });

  it("starts chapters on stage boundaries so the scene ramps stay untouched", () => {
    const starts = STAGES.map((s) => s.start as number);
    for (const c of CHAPTERS) expect(starts).toContain(c.p);
  });

  it("keeps claims neutral through chapter 1 and reveals every verdict by the end of chapter 2", () => {
    for (const status of ["supported", "contradicted", "unsupported", "review"] as const) {
      expect(statusReveal(status, storyProgress(0.33))).toBe(0);
      expect(statusReveal(status, storyProgress(2 / 3))).toBe(1);
    }
    expect(statusReveal("contradicted", 0.56)).toBeGreaterThan(0);
    expect(statusReveal("contradicted", 0.56)).toBeLessThan(1);
  });

  it("stores a clamped scroll fraction and notifies only on change", () => {
    const store = createSceneStore();
    let calls = 0;
    const off = store.subscribe(() => { calls += 1; });
    store.set(0.5);
    store.set(0.5);
    store.set(3);
    store.set(-2);
    expect(store.get()).toBe(0);
    expect(calls).toBe(3);
    off();
    store.set(0.25);
    expect(calls).toBe(3);
  });

  it("keeps the free region sane without notifying subscribers", () => {
    const store = createSceneStore();
    let calls = 0;
    store.subscribe(() => { calls += 1; });
    expect(store.region).toEqual({ left: 0, right: 1, top: 0, bottom: 1 });
    store.setRegion({ left: 0.55, right: 1, top: 0, bottom: 1 });
    expect(store.region).toEqual({ left: 0.55, right: 1, top: 0, bottom: 1 });
    store.setRegion({ left: 0.95, right: 0.9, top: 0.7, bottom: 0.2 }); // inverted or degenerate measurements never collapse the region
    expect(store.region.right - store.region.left).toBeCloseTo(0.2, 6);
    expect(store.region.bottom - store.region.top).toBeCloseTo(0.2, 6);
    expect(calls).toBe(0);
  });
});
