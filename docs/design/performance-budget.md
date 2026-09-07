# Performance Budget

## Landing page

| Metric | Budget |
|---|---|
| LCP (static hero SVG) | < 2.5s on a mid-range laptop, 4G throttled |
| CLS | < 0.05 (the caption slot has a fixed height so chapter changes never move the copy) |
| INP | < 200ms |
| JS on first load (excluding scene chunk) | ≤ 180 KB gzip |
| Scene chunk (three + r3f + drei subset + scene) | ≤ 420 KB gzip, lazy, `ssr:false`, fetched after first paint; never fetched for reduced-motion, no-WebGL, or paused visitors |
| Hero scroll length | 200svh (`md`+), 180svh below; the story reads in three scrolls |
| Fonts | 3 families, subset latin, `display: swap`, self-hosted via `next/font` |
| Images | none required; OG image only |
| Frame time | ≤ 16ms tier 3/2, ≤ 22ms tier 1; auto-degrade otherwise (90-frame average, deltas > 100ms ignored) |
| GPU | DPR capped per tier; bloom and vignette only at tiers 2 and 3 and only after the eighth visible frame; transmission material and shadows only at tier 3; ≤ 16 draw calls in the scene |
| Idle GPU | zero frames while the hero is off screen (`frameloop="demand"` via IntersectionObserver) or paused (canvas unmounted) |
| Scroll handling | one passive listener, one rAF per event, writes a store; React re-renders the hero only when the chapter (1 of 3) changes |

## Application

| Metric | Budget |
|---|---|
| Route JS | ≤ 220 KB gzip per route; charts and viewer code-split |
| Table render | 500 rows without virtualization; > 500 virtualized |
| API round-trip for ledger | < 300ms local; TanStack Query caching with `staleTime` 10s |
| Polling | job status every 1.5s while running, stops on terminal state |

## Practices

- `next/dynamic` for the scene, charts, document viewer, and report export.
- Instanced geometry; `Points` for particles; `frameloop="demand"` when offscreen; the canvas starts in `demand` until it is seen.
- Defer expensive effects until the thing they decorate has been seen: post-processing mounts after the scene has drawn on screen.
- Give visitors an off switch for heavy visuals and remember it (`localStorage` `bc.scene.paused`).
- No layout thrash: read layout in effects once; animate transforms only.
- `content-visibility: auto` on landing sections below the fold.
- Static landing figures come from a committed JSON snapshot, not the API.
- CI runs `next build`; bundle budgets are checked by hand against the build output (no automated size gate yet).
- `apps/web/scripts/scene-check.mjs` (against a running dev server) screenshots the three chapters, prints the active caption at each stop, and toggles the pause control; run it after any change to the hero or scene.
