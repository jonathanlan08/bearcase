# Performance Budget

## Landing page

| Metric | Budget |
|---|---|
| LCP (static hero SVG) | < 2.5s on a mid-range laptop, 4G throttled |
| CLS | < 0.05 |
| INP | < 200ms |
| JS on first load (excluding scene chunk) | ≤ 180 KB gzip |
| Scene chunk (three + r3f + drei subset + scene) | ≤ 420 KB gzip, lazy, `ssr:false`, fetched after first paint |
| Fonts | 3 families, subset latin, `display: swap`, self-hosted via `next/font` |
| Images | none required; OG image only |
| Frame time | ≤ 16ms tier 3/2, ≤ 22ms tier 1; auto-degrade otherwise |
| GPU | DPR capped per tier; no post-processing; ≤ 12 draw calls in the scene |

## Application

| Metric | Budget |
|---|---|
| Route JS | ≤ 220 KB gzip per route; charts and viewer code-split |
| Table render | 500 rows without virtualization; > 500 virtualized |
| API round-trip for ledger | < 300ms local; TanStack Query caching with `staleTime` 10s |
| Polling | job status every 1.5s while running, stops on terminal state |

## Practices

- `next/dynamic` for the scene, charts, document viewer, and report export.
- Instanced geometry; `Points` for particles; `frameloop="demand"` when offscreen.
- No layout thrash: read layout in effects once; animate transforms only.
- `content-visibility: auto` on landing sections below the fold.
- Static landing figures come from a committed JSON snapshot, not the API.
- CI runs `next build` and fails on bundle budget regressions (size check script).
