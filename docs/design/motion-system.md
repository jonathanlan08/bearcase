# Motion System

Library: `motion` (DOM) and React Three Fiber (`useFrame`) for the scene. Motion has a job: reveal structure, draw relationships, confirm actions. It never entertains.

## Tokens

| Token | Value | Use |
|---|---|---|
| `dur-micro` | 120ms | hover, press, chip toggle |
| `dur-std` | 200ms | menus, drawers, table row focus |
| `dur-emph` | 320ms | dialogs, section reveals |
| `dur-cine` | 700–900ms | landing figure choreography, hairline draws |
| `ease-std` | `cubic-bezier(0.2, 0, 0, 1)` | most transitions |
| `ease-reveal` | `cubic-bezier(0.32, 0.72, 0, 1)` | text-mask and figure reveals |
| `ease-exit` | `cubic-bezier(0.4, 0, 1, 1)` | exits, always shorter than enters |

No spring overshoot anywhere. Exits are ≤ 60% of the matching enter duration.

## Vocabulary

1. **Text-mask reveal** — headline lines clip-reveal from baseline, 40ms stagger per line, `ease-reveal`, once.
2. **Typography stagger** — paragraphs/lists fade+8px rise, 30ms stagger, once on scroll-in (threshold 0.3).
3. **Hairline draw** — SVG path `stroke-dashoffset` from full to 0, `dur-cine`; terminal square fades in after the line arrives. Used for every claim→evidence link.
4. **Value scrub** — numbers count from previous to next value over 500ms, mono tabular so width is stable; screen readers receive only the final value (`aria-live` off during scrub, final set once).
5. **Chart morph** — bars interpolate height; DSCR needle sweeps; threshold rule static.
6. **Report assembly** — sections slide in from 12px below, 60ms stagger, citation chips appear last.
7. **Citation highlight** — 2px `signal` outline + `paper-100` fill on the cited evidence, 120ms; persists while focused.
8. **Route transition (app)** — content crossfade 150ms; rail and header are static. No slide.
9. **Table row transitions** — status change: glyph swaps with 120ms crossfade; row background flash `paper-100` 320ms then settles.

## Landing choreography (per section)

- Hero: DOM copy reveals in the first 900ms (label → headline lines → support → CTAs); the scene runs its own stage timeline tied to scroll (see `3d-evidence-core.md`).
- Sections 2–6: label and H2 reveal first; figure choreography starts when 40% visible and plays once; interactive controls remain live afterwards.

## Reduced motion (`prefers-reduced-motion: reduce`)

- All reveals become 120ms opacity-only or instant.
- Hairlines render fully drawn. Value scrub disabled (final value set immediately). Charts render final state.
- Scene: static frame; scene caption becomes a list.
- Live regions still announce final states.

## Implementation notes

- Use `motion`'s `useReducedMotion()` and a global `MotionConfig reducedMotion="user"`.
- Animate only `transform`, `opacity`, `stroke-dashoffset`, and SVG attributes. Never `width/height/top/left`.
- Scroll-linked values via `useScroll` + `useTransform`; no `scroll-snap` on the landing page.
- `will-change` only on elements currently animating; remove after.
