# Landing Page Specification (`/`)

World: **Ink**. Container 1200px. Section rhythm 128px desktop / 96px tablet / 72px mobile. Every section has a mono micro-label (`01 · CLAIMS`), a serif H2, one paragraph, and one *evidence figure* — a real rendering of Northstar output, never a fake screenshot.

## Route map (public)

| Route | Purpose |
|---|---|
| `/` | Landing page (this spec) |
| `/demo` | Redirect into the seeded Northstar deal (`/app/deals/{seed}`), creating a demo session |
| `/methodology` | Formulas, AI/code boundary, citation approach, limitations |
| `/github` | Redirect to the repository |

## Global chrome

- **Nav (site):** left wordmark + Evidence Link symbol; right: `Methodology`, `GitHub`, primary button `Explore the demo`. 64px tall, transparent over the hero, becomes `ink-950/85` with hairline bottom after 80px scroll. Mobile: wordmark + demo button + menu (dialog).
- **Footer:** three columns — product (Demo, Methodology, GitHub), disclosure ("Northstar HVAC is fictional. BearCase is an educational prototype and does not provide financial, legal, tax, or investment advice."), and the build/model notice (mock vs Anthropic mode). Mono micro-labels.
- **Skip link** to `#main` as the first focusable element.

## Sections

### 0. Hero — The Evidence Core

- Layout: full-viewport (`min-h-[100svh]`), two layers. Layer A: WebGL canvas (see `3d-evidence-core.md`), positioned right-of-center on desktop, centered behind text on mobile at reduced density. Layer B: DOM copy, left-aligned, max-width 640px.
- Copy: micro-label `AI-ASSISTED ACQUISITION DILIGENCE`; display headline "Stress-test every claim *before capital moves.*" (italic serif on the emphasized phrase); support line; CTA row: primary `Explore the demo` (→ `/demo`), secondary `View on GitHub`.
- Under the CTAs: a *scene caption* — a mono line that names the current storyboard stage ("03 · Evidence flows into the core") — updated by the scene, `aria-live="polite"` but throttled to once per stage.
- Scroll: the hero section is 240vh tall; the canvas is sticky for the first 100vh while the storyboard progresses with scroll position (0 → 1). No scroll hijacking: native scrolling, the scene merely reads `scrollY`. A thin vertical progress rule (1px, 10 ticks) at the left edge shows stage progress.
- Reduced motion / no WebGL: static composed frame (SVG) of stage 8 (model + covenant warning) with the same copy; stage caption becomes a static list of the ten stages.

### 1. Product proof (real capabilities)

Three-column strip of real facts drawn from the repository, mono-labeled, no vanity numbers: "4 claim statuses · absence of evidence is not contradiction", "Deterministic engine · 14 documented formulas", "Every material statement cited or labeled as derived". Each links to `/methodology`.

### 2. Claim → evidence workflow

Split figure: left, a claim card ("Revenue has grown ~18% annually since 2022", CIM p.3, status Contradicted); right, the evidence — FY22–FY24 revenue cells from the statements XLSX with the recomputed CAGR 11.6%. A citation hairline is drawn from claim to cells on scroll-in. Copy explains extraction → linking → status.

### 3. Contradiction detection

Figure: a two-source comparison — CIM p.5 "No single customer exceeds 10%" against the customer CSV aggregate showing Apex Logistics Park at 22.0%. Both sources highlight together on hover/focus of the contradiction chip. Copy: statuses, the rule that missing evidence ≠ contradiction, human review.

### 4. Financial verification and add-back waterfall

Figure: the waterfall — Reported EBITDA $1.64M → +$105K owner comp (accepted) → +$65K litigation (accepted) → $130K temp labor (rejected, hatched) → $95K marketing (review) → $65K integration (unsupported) → Verified $1.81M vs Seller $2.10M. Bars animate in sequence on scroll-in; rejected bars stay hatched and outside the running total.

### 5. Scenario Lab

Figure: a compact scenario panel — sliders for customer loss and margin compression with a DSCR readout that morphs from 1.34x (base) to 0.93x (downside) as the user drags, and the 1.25x threshold line. Interactive on desktop; on mobile it plays a scripted before/after with a play control.

### 6. Investment-committee report assembly

Figure: report sections assembling in order (overview, verified financials, contradictions, scenarios, questions, citations), each with citation chips. Copy: reproducibility, immutability of AI output, reviewer decisions.

### 7. Methodology, open source, technical credibility

Three columns: AI vs deterministic responsibilities; the trust rules; the stack (FastAPI, PostgreSQL-compatible SQLAlchemy, Next.js, Anthropic API with mock mode). Links to `/methodology` and GitHub.

### 8. Final CTA

Serif line "Open the fictional Northstar deal." + primary/secondary CTAs + the disclosure line.

## Section states

- Figures render server-side from committed JSON snapshots (`apps/web/src/content/northstar-snapshot.json`) so the landing page never depends on the API being up.
- Each figure has a `<figcaption>` and a static SVG/HTML alternative for reduced motion.

## Acceptance checklist

- [ ] Hero explains the workflow to a first-time viewer within one scroll.
- [ ] All figures use real Northstar values and the fictional label.
- [ ] No fake logos/testimonials/metrics.
- [ ] Reduced-motion and no-WebGL renders are complete.
- [ ] Lighthouse: LCP < 2.5s on a mid-range laptop, CLS < 0.05.
