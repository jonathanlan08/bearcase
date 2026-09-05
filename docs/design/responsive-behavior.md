# Responsive Behavior

Breakpoints (Tailwind v4 defaults, mobile-first): `sm` 640, `md` 768, `lg` 1024, `xl` 1280, `2xl` 1536. Test at 375, 768, 1024, 1440.

## Landing page

| Element | < 768 | 768–1023 | ≥ 1024 |
|---|---|---|---|
| Hero layout | copy stacked above canvas; canvas 60vh, tier ≤1 | copy left 55%, canvas right | copy left 45%, canvas right 55%, sticky |
| Hero height | 180vh | 220vh | 240vh |
| Display size | 44px | 64px | up to 104px |
| Section figures | single column, figure below copy, horizontal scroll for wide tables | two columns | two columns, figure 7/12 |
| Scenario figure | scripted before/after with play button | interactive | interactive |
| Nav | wordmark + demo + menu dialog | full | full |

## Application

| Element | < 768 | 768–1023 | ≥ 1024 |
|---|---|---|---|
| Shell | top bar + bottom tab bar (5 items) | icon rail 56px | rail 232px (collapsible) |
| Claim Audit | ledger list; selecting a claim pushes the evidence panel as a full-height sheet with back button | split 45/55 | split 40/60 |
| Financial tables | horizontal scroll container with sticky first column; column count preserved | same | full |
| Scenario Lab | assumptions accordion above results; sensitivity grid scrolls horizontally | two columns | two columns + grid below |
| Report | TOC as a select at top; content full width | TOC drawer | sticky TOC left |
| Document viewer | full-screen sheet | drawer 60% | drawer 50% |
| Dialogs | full-screen sheets | centered 520px | centered 560px |

## Rules

- Never horizontal page scroll; wide content scrolls inside its own container with visible affordance (fade edge + scroll hint).
- Touch targets ≥ 44×44 with ≥ 8px spacing on touch devices; tables use 48px rows on touch.
- Type scale uses `clamp()`; body never below 16px on mobile.
- Safe areas: bottom tab bar and sheets use `env(safe-area-inset-bottom)`.
- Images/SVG figures reserve aspect ratio (`aspect-[16/10]`) to hold layout.
- Orientation: landscape phones treat as `md` for layout but keep tier ≤1 for the scene.
