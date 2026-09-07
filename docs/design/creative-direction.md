# BearCase AI — Creative Direction

Status: accepted design source of truth for implementation. Every other file in `docs/design/` derives from this one.

## 1. Positioning in one line

BearCase is the instrument an analyst picks up when a deal looks good on paper. The brand should feel like a precision instrument, not a chatbot: quiet, exact, unhurried, and hard to fool.

Headline: **Stress-test every claim before capital moves.**
Support: BearCase audits deal documents, verifies financial assumptions, and exposes the downside with source-linked evidence.

## 2. The concept: *Ink and Paper*

Two worlds, deliberately contrasted:

| Surface | World | Feel | Why |
|---|---|---|---|
| Public site (`/`, `/methodology`) | **Ink** — near-black, cinematic, spacious | A darkened review room where evidence is projected and examined | Cinematic storytelling needs depth and light; contradiction signals read strongest against ink |
| Application (`/app/...`) | **Paper** — warm off-white workbench, dense, calm | A ledger on a desk under good light | Analysts read tables for hours; warm paper and graphite text reduce fatigue and signal "financial document", not "dashboard toy" |

The transition from Ink to Paper *is* the product story: the site dramatizes what the tool does; the tool itself is a ledger. The app ships a dark option, but Paper is the default.

## 3. Visual qualities (priority order)

1. **Editorial simplicity** — one idea per section, large type, long measure, no decoration without function.
2. **Provenance made visible** — every number is drawn as *something that came from somewhere*. A hairline connecting a claim to its source is the signature motif.
3. **Restrained color** — the palette is neutral; color is spent only on status (supported / review / contradicted) and one technical accent.
4. **Material honesty** — flat surfaces, hairline borders, matte materials in 3D. No blur stacks, no neon, no decorative gradients.
5. **Precise motion** — motion draws lines, reveals type, and scrubs numbers. It never bounces.
6. **Financial credibility** — tabular numerals everywhere; units and periods always labeled; signed values always signed.

## 4. Anti-patterns (hard rules)

- No purple/indigo AI gradients, no neon cyberpunk, no glassmorphism stacks, no floating-card clutter.
- No fake logos, testimonials, metrics, or "trusted by" strips. Product proof is the real Northstar demo output, labeled fictional.
- No cartoon bear, no stock-market bear, no bull/bear iconography. "Bear" lives in the name only; the symbol is an evidence link.
- No imitation of Apple layouts, assets, or typography.
- No motion for its own sake: if an animation does not explain a relationship or confirm an action, remove it.
- No eyebrow labels, section numbers, decorative middle-dot strips, or scroll cues. Headings carry their own weight.
- Status is never conveyed by color alone (see `accessibility.md`).

## 5. Brand system summary

- **Wordmark:** `BearCase` in Geist Medium, tracking −0.02em. "AI" is never set in the wordmark; it appears as a mono micro-label (`AI · DILIGENCE`) where context needs it.
- **Symbol — the Evidence Link:** two small filled squares (source, claim) on a diagonal, joined by a hairline with a hollow node at the midpoint (the core). Legible at 16px. Used as favicon, in navigation, and as the loading indicator (the line draws itself).
- **Palette:** see `design-system.md`. Ink `#07080A` ↔ Paper `#F5F2EC`. Accent *Signal* `#7FB2FF` (on ink) / `#2B6CD9` (on paper). Status: supported = signal, review required = amber, contradicted = red, unsupported = graphite.
- **Type:** one family. Geist at 600 with tight tracking for display and headings, Geist at 400/500 for UI and body, Geist Mono only for numbers and citations. No serif, no italic accent words, no uppercase eyebrow labels.
- **Signature motif:** the citation hairline — a 1px line from a claim to its evidence with a small square terminal at the source end.

## 6. Voice

Short declaratives. Present tense. Financial vocabulary used correctly. No exclamation marks. Never "AI-powered"; say what code does and what the model does. Disclaimers are plain and visible, not buried.

## 7. Decisions implementation must preserve

1. Ink public site / Paper application split.
2. The Evidence Sculpture hero communicates the ten-step workflow; it is not a decorative object.
3. The citation hairline recurs in 3D, in landing sections, and in the app's claim–evidence split view.
4. Status system: shape + label + color; four claim states, two covenant states.
5. Tabular numerals with explicit units and periods everywhere.
6. Reduced-motion and no-WebGL versions are complete designs, not degraded ones.
