# Accessibility

Target: WCAG 2.2 AA across site and app. Accessibility is part of the definition of done for every component.

## Structure and navigation

- Semantic landmarks: `header`, `nav[aria-label]`, `main#main`, `aside`, `footer`. One `h1` per route.
- Skip link first in DOM. Focus moves to `h1` on client-side route change (app) and is announced.
- Keyboard: every action reachable by keyboard with a visible 2px `signal` focus ring, offset 2px. No focus traps except dialogs (which trap and restore focus). Tab order equals visual order.
- Shortcuts are single keys only when focus is in the ledger; `?` opens the shortcut sheet; shortcuts never override native form editing.

## Status without color

Every status renders a glyph (shape) + text label + color. Tables with a glyph-only "Status" column set `aria-label` on the cell. Charts use fills + glyphs + signed values; a table alternative is always available via a toggle next to the chart.

## Contrast

- Text ≥ 4.5:1; large text and UI boundaries ≥ 3:1. Tokens in `design-system.md` were chosen against `paper-50` and `ink-950`.
- Muted text uses `graphite-500` on paper, `graphite-400` on ink; never lighter.
- Dark app theme reuses the ink tokens with paper text; hairlines `ink-600` satisfy 3:1 against `ink-900`.

## Forms

- Labels visible above inputs; helper text below; errors adjacent with an icon and `aria-describedby`; error summary at top with links on submit.
- Units are part of the input (suffix) and the accessible name ("Interest rate, percent").
- No placeholder-only labels.

## Motion

- `prefers-reduced-motion` honored globally (see `motion-system.md`); no content depends on motion to be understood.
- No flashing above 3 Hz; contradiction pulse is 0.8 Hz and stops after 3 cycles.

## 3D hero

- `canvas role="img" aria-label`; DOM caption mirrors the current stage; keyboard node list mirrors clickable nodes; static SVG alternative with `<title>` and `<desc>`.

## Screen-reader status

- Processing progress: `role="progressbar"` with `aria-valuenow`; job state changes announced via one polite live region per page.
- Review actions: confirmation announced ("Claim accepted. Decision recorded.").
- Value scrub: final values only.

## Touch

- Targets ≥ 44px; swipe gestures always have a button equivalent; drag rotation on the canvas has no functional payload.

## Testing gates

- `eslint-plugin-jsx-a11y` (via `eslint-config-next`) clean.
- Playwright smoke: keyboard-only traversal of Claim Audit (select claim, jump to evidence, accept) passes.
- Manual: VoiceOver pass on Deal Room and Claim Audit before release.
