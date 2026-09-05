# BearCase Design System

Tokens are the contract between design and code. Implementation lives in `apps/web/src/app/globals.css` (`@theme`) and must match this file.

## 1. Color

### 1.1 Neutrals

| Token | Hex | Use |
|---|---|---|
| `ink-950` | `#07080A` | Public site page background |
| `ink-900` | `#0D0F12` | Public site section background, app dark background |
| `ink-800` | `#15181D` | Dark surface |
| `ink-700` | `#1F242B` | Dark elevated surface |
| `ink-600` | `#2C333C` | Dark borders, hairlines |
| `graphite-500` | `#6B7480` | Muted text on paper (4.9:1 on `paper-50`) |
| `graphite-400` | `#8A94A0` | Muted text on ink (5.6:1 on `ink-950`); unsupported status |
| `paper-50` | `#F5F2EC` | App page background; primary text on ink (15.8:1) |
| `paper-100` | `#ECE8E0` | App muted surface |
| `paper-200` | `#DDD8CE` | App borders, hairlines |
| `paper-0` | `#FBFAF7` | App cards / raised surface |
| `ink-text` | `#0D0F12` | Primary text on paper (17:1) |

### 1.2 Accent and status

| Token | On ink | On paper | Meaning |
|---|---|---|---|
| `signal` | `#7FB2FF` | `#2B6CD9` | Interactive accent; **Supported** claim |
| `amber` | `#E5A83B` | `#B7791F` | **Review required**; covenant *warning* |
| `red` | `#E5644E` | `#C0392B` | **Contradicted**; covenant *breach* |
| `graphite` | `#8A94A0` | `#6B7480` | **Unsupported** (evidence absent) |

Contrast: every "on paper" value ≥ 4.5:1 against `paper-50`; every "on ink" value ≥ 4.5:1 against `ink-950`. Text-on-status-fill uses the neutral text color of the surface, never white on amber.

### 1.3 Status glyphs (non-color cue, required)

| Status | Shape | Glyph | Label |
|---|---|---|---|
| Supported | filled circle | ✓ | "Supported" |
| Contradicted | filled diamond | ! | "Contradicted" |
| Unsupported | dashed hollow circle | – | "Unsupported" |
| Review required | outlined square | ? | "Review required" |
| Covenant warning | outlined triangle | ! | "Below threshold" |

Glyphs are inline SVG (`StatusGlyph` component), 14px in tables, 16px in headers, always followed by the text label unless inside a table cell whose column header is "Status" and the cell has an `aria-label`.

### 1.4 Charts

Series palette (order): `signal`, `graphite`, `amber`, `red`. Seller-stated values are always **graphite outlined**; verified values are always **signal filled**. Increases/decreases in waterfalls use signed labels and ▲/▼ glyphs plus fill (signal for adds accepted, graphite hatched for rejected).

## 2. Typography

| Role | Family | Size / line | Weight | Tracking |
|---|---|---|---|---|
| Hero display | Geist | 40 / 76px, line 1.02 | 600 | −0.035em |
| H1 | Geist | 30 (mobile 26) | 600 | −0.03em |
| H2 | Geist | 30 / 36 | 600 | −0.03em |
| H3 | Geist | 20 / 28 | 500 | −0.01em |
| Body | Geist | 16 / 24 (site 17 / 27) | 400 | 0 |
| Small | Geist | 14 / 20 | 400 | 0 |
| Small label | Geist | 12 / 16 | 500 | 0, sentence case |
| Numeric | Geist Mono | inherits | 400/500 | 0, `tabular-nums` |
| Citation chip | Geist Mono | 12 / 16 | 500 | 0 |

Rules: numbers in tables are always Geist Mono tabular; currency uses `$12.95M` style in narrative and `12,950,000` in tables; percentages carry one decimal (`11.6%`); multiples carry an `x` (`1.33x`).

## 3. Layout

- Container: 1200px max on the site (`px-6` mobile, `px-10` tablet, `px-16` desktop); the app is fluid to 1600px.
- Site grid: 12 columns, 24px gutter. App grid: 12 columns, 16px gutter.
- Spacing scale (4px base): 4, 8, 12, 16, 24, 32, 48, 64, 96, 128. Site sections use 96–128 vertical rhythm; app panels use 16–24.
- Split view: claim list 40% / evidence 60% at ≥1024px; stacked with a segmented control below.

## 4. Shape and depth

- Radii: one scale, `r-1` 4px (inputs, chips), `r-2` 6px (cards, buttons), `r-3` 8px (panels, dialogs). No pills.
- Borders: 1px hairlines (`paper-200` on paper, `ink-600` on ink). Hairlines carry structure; shadows do not.
- Shadows: app only — `shadow-1: 0 1px 2px rgba(13,15,18,.06)`, `shadow-2: 0 8px 24px rgba(13,15,18,.10)` for menus and dialogs. Site: none.
- Focus ring: 2px `signal` outline offset 2px, on every operable element.

## 5. Materials (3D and illustration)

- Document planes: matte paper, `paper-50` at 92% opacity, thin `ink-600` edge.
- Spreadsheet cells: flat `paper-100` quads with `graphite-400` grid lines.
- Analysis core: translucent fresnel shell (`signal` rim, `ink-800` body, 35% opacity), no bloom.
- Evidence lines: 1px `graphite-400` at rest, `signal` when active; contradiction lines `red`; review lines `amber`, dashed.
- Particles: 1–2px `paper-50` points at 40–60% opacity.

## 6. Iconography

Lucide icons at 16/20px, stroke 1.5. Icons never appear without a visible label or `aria-label`. Emoji are never used as icons.

## 7. Component tokens (summary)

| Component | Height | Padding | Radius | Notes |
|---|---|---|---|---|
| Button primary | 40 (44 touch) | 0 16 | r-1 | `ink-text` on `signal` (paper) / `ink-950` on `signal` (ink) |
| Button secondary | 40 | 0 16 | r-1 | 1px hairline, transparent |
| Input | 40 | 0 12 | r-1 | label always visible above |
| Table row | 40 | 0 12 | — | zebra off; hover `paper-100` |
| Status chip | 24 | 0 8 | r-full | glyph + label |
| Citation chip | 22 | 0 6 | r-1 | mono, `paper-100` fill, keyboard-operable |
| Panel | — | 16–24 | r-3 | hairline, `paper-0` fill |
