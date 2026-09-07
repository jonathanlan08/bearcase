# Landing Page Specification (`/`)

World: **Ink**. Container 1200px. Section rhythm 128px desktop / 96px tablet / 72px mobile. Every section has a Geist H2 in sentence case, one paragraph, and one *evidence figure*: a real rendering of Northstar output, never a fake screenshot. No eyebrows, no section numbers, no dot strips, no serif, no pills, no gradients on surfaces (the 2026-09-06 design pass removed them). Each section uses a distinct layout (split, full width, stacked, split reversed, definition list) so the page does not read as a template.

The page has one job for a first-time viewer: say that this is for checking a seller's story before buying a business, and get them into the demo. Demo facts in the copy (claim counts, EBITDA figures, scenarios below the covenant) are computed from the committed snapshot the figures render from, so the words cannot drift from the pictures.

## Route map (public)

| Route | Purpose |
|---|---|
| `/` | Landing page (this spec) |
| `/demo` | Creates a visitor-owned demo session and redirects into that visitor's copy of the Northstar deal (`/app/deals/{id}`); explains the first-visit wait; on failure gives a visitor-facing reason, the HTTP code, Retry, and Home |
| `/methodology` | "How we check claims": statuses, the AI/code boundary, formulas, what a citation means, limits |
| `/github` | Redirect to the repository |

## Global chrome

- **Nav (site):** left wordmark + Evidence Link symbol; right: `Methodology`, `Open your workspace` (→ `/app`), primary button `Explore the demo`. 64px tall, transparent over the hero, becomes `ink-950/85` with hairline bottom after 80px scroll. Mobile: wordmark + demo button + menu (dialog with Methodology, Open your workspace, Explore the demo; Escape closes).
- **Footer:** three columns — a one-line description ("Checks a seller's claims against the documents before you buy a business. Open source, MIT licensed."), product links (Explore the demo, Open your workspace, Methodology, View on GitHub), and the disclosure ("Northstar HVAC Services and every person, customer, contract, lender, and number in the demo are fictional. BearCase is an educational prototype and does not provide financial, legal, tax, or investment advice.") with the model notice (rule-based by default, so the demo needs no API key; add a provider key for a live model). GitHub lives here, not in the hero or nav.
- **Skip link** to `#main` as the first focusable element.

## Sections

### 0. Hero — The Evidence Sculpture

- Layout: full-viewport (`min-h-[100svh]`), two layers. Layer A: WebGL canvas (see `3d-evidence-sculpture.md`), framed so the composition sits right of the copy on wide screens and above it in portrait, with a darker scrim on mobile so the copy stays readable. Layer B: DOM copy, left-aligned, max-width 600px. The headline and the actions sit over the calm part of the scene, never over the core.
- Copy: display line "Stress-test every claim before capital moves." Support line: "Buying a business? Check whether the seller's story matches the documents: overstated earnings, missing evidence, and what happens when the numbers get worse."
- CTA row: primary `Explore the demo` (→ `/demo`); secondary `Open your workspace` (→ `/app`, sign in or create an account).
- **Story captions:** the scene is told in three chapters, one scroll each (`CHAPTERS` in `storyboard.ts`): "Seller says 18% growth" (the memo claims 18% annual growth; BearCase quotes the claim and links it to the page it came from), "The statements show 11.6%" (recomputed from the income statement; the claim is marked contradicted), "Open the evidence" (every figure links to the cell it came from, then feeds the model, the downside case, and the report). They render as an ordered list of HTML captions (`aria-label="How BearCase reviews a claim"`) outside the busy centre of the scene: at the top of the hero on narrow screens, at the bottom left on wide ones. The active step carries `aria-current="step"`, a 2px left rule in `signal`, and heavier type, so the state is never colour alone; on wide screens it also shows its one-line detail in a fixed-height slot so the copy above never shifts. A polite `aria-live` region announces "Step 2 of 3: The statements show 11.6%." with the detail. The same words appear on every rendering path, including the static composition.
- **Pause control:** a small secondary button beside the captions, `--radius-1`, icon plus text "Pause 3D" / "Resume 3D", `aria-pressed` reflecting the state. Paused unmounts the scene (stopping the render loop and freeing the GPU context) and shows the static composition with the copy and captions unchanged. The choice is remembered in the browser (`bc.scene.paused`) across visits.
- Scroll: the hero section is 200svh tall on desktop and 180svh on mobile; the canvas is sticky for the first 100svh while scroll position drives the chapters (each chapter owns one third of the scroll, mapped onto the ten fine-grained stages the scene animates against). No scroll hijacking: native scrolling; the hero writes the scroll fraction to a small external store the scene reads every frame without re-rendering React, and only a chapter change re-renders the captions. Rendering stops when the canvas leaves the viewport; bloom and vignette switch on only after the scene has been visible and stable.
- Reduced motion / no WebGL / paused: static composed frame (SVG, with `<title>` and `<desc>`) showing the same three states, with labels on the memo ("CIM: 18% growth claimed") and the statements ("Statements: 11.6% a year"), the growth claim's red evidence line running from one to the other, the model grid with the covenant row, and the report stack; the copy and captions are unchanged.

### 1. Buying a business? (framing and the first session)

Heading "The seller's story, checked line by line against the paperwork." (the "Buying a business?" line is the hero subhead; the CTAs live in the hero and the closing section) One paragraph in plain words: BearCase reads what the seller hands over, quotes each claim next to the page or cell behind it, recomputes the numbers with plain code, and shows where the story and the evidence disagree; overstated earnings, one customer that is most of the revenue, and loan payments the cash will not cover show up before you sign. CTAs `Explore the demo` and `Open your workspace`, then "Try a fictional deal. No account or API key needed."

Below, "What your first session looks like": a four-step ordered list in a four-column grid — Add documents (what to upload), Check the findings (statuses with the page or cell beside each), Test the downside (lose the largest customer or squeeze margins, see whether the cash still covers the loan), Export the review (a report for a lender, partner, or committee, cited and with every decision recorded).

### 2. Every claim gets a source (split)

Left, the copy: BearCase quotes each material claim from the sales memo, the buyer's model, the loan term sheet, and the contracts, links it to the page, sheet, row, or cell it came from, then checks what the primary sources say. Right, the figure: a claim card ("Revenue has grown ~18% annually since 2022", CIM p.3, status Contradicted) beside FY22–FY24 revenue cells from the statements XLSX with the recomputed CAGR 11.6%; a citation hairline is drawn from claim to cells on scroll-in.

### 3. Two documents, one disagreement (full width)

Copy: numbers are recomputed from the statements and the customer file by deterministic code; narrative claims are compared only with evidence retrieved from the documents; a claim ends up supported, contradicted, unsupported, or with a reviewer, and the rule that decided is always shown; missing evidence is never counted as a contradiction. Figure: CIM p.5 "No single customer exceeds 10%" against the customer CSV aggregate showing Apex Logistics Park at 22.0%; both sources highlight together on hover/focus of the contradiction chip.

### 4. Adjusted EBITDA, adjusted back (stacked)

Copy: sellers add back costs they say will not recur, which makes earnings look larger; each add-back is tested against the statement lines it claims to normalize; the price multiple, the debt load, and the loan coverage follow from the verified figure. Figure: the bridge — Reported EBITDA $1.64M → +$105K owner comp (accepted) → +$65K litigation (accepted) → $130K temp labor (rejected, hatched) → $95K marketing (review) → $65K integration (unsupported) → Verified $1.81M vs Seller $2.10M, on a truncated axis. Bars animate in sequence on scroll-in; rejected bars stay hatched and outside the running total.

### 5. Find the downside before the lender does (split reversed)

Copy: base, downside, and severe cases share one five-year model with named inputs; move an assumption and the engine recomputes revenue, earnings, the cash available for the loan, coverage against the lender's minimum, and returns; every run stores an immutable snapshot of its inputs. Figure: a compact scenario panel — sliders for customer loss and margin compression with a DSCR readout that moves from 1.34x (base) toward the downside as the user drags, and the 1.25x threshold line. Interactive on desktop; on mobile a scripted before/after with a play control.

### 6. A review the committee can check

Copy: verified financials, the claim ledger, contradictions, unsupported assumptions, customer concentration, adjustments, scenarios, risks, open questions for the seller, and every reviewer decision, with citations that open the source; ask the deal a question in plain language and get the same discipline back. Figure: report sections assembling in order, each with citation chips.

### 7. The model reads. The code counts. The reviewer decides. (definition list)

Four terms: reading and quoting (the model classifies, quotes with a source, ranks evidence, drafts questions and narrative; it never produces a financial number), every number (deterministic code, cell-level provenance, missing inputs stay missing), every citation (schema validation, uncited statements fail the report, immutable AI output, additive audited decisions), untrusted documents (validated, never executed, instruction-like text stored inert and reported). One link: `Read how claims are checked` (→ `/methodology`).

### 8. Close

"Open the fictional Northstar deal." followed by one paragraph of counts computed from the snapshot (headline claims, how many contradicted by the seller's own documents, add-backs tested with the seller's and the verified EBITDA, scenarios below the lender's minimum; numbers in words where small, figures in `num`), CTAs `Explore the demo` and `Open your workspace`, "Try a fictional deal. No account or API key needed.", and the disclosure line.

## Section states

- Figures render server-side from committed JSON snapshots (`apps/web/src/content/northstar-snapshot.json`) so the landing page never depends on the API being up; the copy's counts come from the same file.
- Each figure has a `<figcaption>` and a static SVG/HTML alternative for reduced motion.

## Acceptance checklist

- [ ] A first-time viewer can say what the product is for ("checking a seller's story before buying a business") from the hero and the framing section alone.
- [ ] The three chapter captions read in order on one scroll of the hero, the active one is marked by more than colour, and the same words appear on the static and paused paths.
- [ ] The pause control switches to the static composition and back, and is reachable by keyboard.
- [ ] All figures and all counts in the copy use real Northstar values and the fictional label.
- [ ] No fake logos/testimonials/metrics.
- [ ] Reduced-motion, no-WebGL, and paused renders are complete.
- [ ] Lighthouse: LCP < 2.5s on a mid-range laptop, CLS < 0.05.
