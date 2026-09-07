# Application Specification (`/app/...`)

World: **Paper** (default), dark option. The app is a ledger: dense, calm, keyboard-first, provenance always one action away. It must also work for someone buying their first business: every screen opens with one sentence that says what it is for and names the next step in plain words, and the two numbers people ask about first (adjusted EBITDA and DSCR) are explained where they appear.

## Route map

| Route | View | Primary object |
|---|---|---|
| `/app` | Deal list + recent activity | Deals |
| `/app/deals/new` | Create deal form | Deal |
| `/app/deals/[dealId]` | Deal overview | Start section, deal summary, status bar, findings digest |
| `/app/deals/[dealId]/documents` | **Deal Room** | Documents, processing jobs |
| `/app/deals/[dealId]/claims` | **Claim Audit** | Claim ledger, evidence split view |
| `/app/deals/[dealId]/financials` | **Financial Verification** | What changed, add-back bridge, metrics, periods |
| `/app/deals/[dealId]/scenarios` | **Scenario Lab** | Sticky result, assumptions, results, sensitivity |
| `/app/deals/[dealId]/report` | **Red-Team Report** | Report sections, citations, export |
| `/app/deals/[dealId]/audit` | Audit history | Review decisions, audit events |

## Shell

- **Desktop (≥1024px):** 232px left rail (collapsible to 56px icon rail; state persisted). Rail: wordmark, deal switcher, five primary nav items, then `Overview` and `Audit history` as secondary, then the mode badge (`MOCK AI` / `ANTHROPIC`) and the fictional-data notice.
- **Tablet:** rail collapsed to icons; labels on hover/focus and in a tooltip.
- **Mobile (<768px):** top bar (deal name, overflow menu) + bottom tab bar with the five primary items (icons + whole-word labels that still say what the screen is: Documents, Claims, Financials, Scenarios, Report; 56px tall, safe-area padded). The floating chat trigger sits above the bar with the safe-area inset included, and page content carries enough bottom padding to scroll clear of both.
- **Page header:** H1 (Geist, sentence case), deal micro-label (`Northstar HVAC · fictional`), one plain sentence under the title saying what the page is for, right-aligned actions.
- **Command palette:** `⌘K` — jump to claim, document, section; run "Process documents", "Generate report".
- **Ask the deal:** `⌘/` (`Ctrl+/` outside Apple platforms) or the floating button opens the chat panel (see §10). Any page can open it with a prompt through `lib/chat-bus.ts`.

## 1. Deal list (`/app`)

Table: Deal, Industry, Purchase price (mono), Documents (n processed/n), Claims (status counts as four mini glyphs), Updated. Row click opens overview. Empty state: Evidence Link symbol, "No deals yet", buttons `Open the Northstar demo` and `Create a deal`. Right column: recent audit events (last 10).

## 2. Create deal (`/app/deals/new`)

Single-column form, labels above inputs, helper text below. Fields: Company name, Industry, Purchase price, Purchase-price basis (radio: *Enterprise value* / *Equity price*), Purchase date, Debt amount, Equity amount, Interest rate (%), Amortization (years), Covenant DSCR threshold (optional, default 1.25). Inline validation on blur; error summary at top on submit failure with links to fields. Live derived line: "Debt/(Debt+Equity) = 60.0%". Required numbers are validated as text first, so a blank field is an error ("Enter the debt amount"), never a silent zero; optional numbers treat blank as not provided; the debt-plus-equity check runs only when all three parse. The basis field is labelled "What the purchase price covers", its help describes each basis in plain words, and the debt-assumed and cash-acquired fields appear only for the equity-price basis. Server validation errors are shown as a plain sentence naming the field, never as raw JSON. One sentence under the title says the figures can be changed later in the Scenario Lab.

## 3. Deal overview

**Start section** (first thing under the header, `aria-labelledby="start-heading"`, raised surface, `--radius-3`, hairline border). Heading, body, and actions change with the deal's state:

- No documents: "Start by adding the seller's documents" — "Upload the financial statements, the sales memo (CIM), the customer list, the contracts, and the loan terms. Run analysis, then check what was found before relying on any number." Action `Add documents`.
- Analysis running: "Analysis is running" — the claims, recomputed numbers, and scenarios appear when processing finishes; the page refreshes on its own. Action `Watch progress in the Deal Room`.
- Documents but no analysis: "Run analysis to check the claims" — "N documents uploaded. Analysis extracts the seller's claims, links each one to its source, recomputes the numbers, and seeds three scenarios." Actions `Run analysis`, `Open the Deal Room`.
- Claims present: "Start with the N claims the documents disagree with" (or "Start with the claims that need a closer look" when nothing is contradicted, or "Every claim checks out so far. Confirm them yourself."), then one sentence with the conflicting, unsupported, and review counts in words. Actions `Review the claims` (→ `/claims`) and, once scenarios exist, `Test a downside scenario` (→ `/scenarios`).
- A `details` disclosure, "New to these numbers?", with two definitions: adjusted EBITDA (earnings before interest, taxes, depreciation, and amortization, adjusted for selected expenses; the seller's adjustments still need review) and DSCR (cash available for debt payments divided by the payments due; at 1.00x there is just enough cash, and the lender may require more).

**Cards** below, in a 2/3-column grid: (a) claim verification — four status counts as a segmented bar with glyphs and labels; (b) adjusted EBITDA — reported, seller adjusted, verified adjusted, as labelled bars; (c) DSCR by scenario with the covenant threshold and a warning or breach glyph; (d) top findings; (e) missing information; (f) documents by state; (g) latest report. Each card links into its section. Numbers use `fmtMoney`/`fmtX` with separators and at most two decimals; ids are never shown on this page.

**Findings** (here, on the report, and in the API) are written for the buyer: the title states what is wrong with formatted figures ("Revenue CAGR is 11.6%, not the 18.0% claimed"; "Downside scenario breaks the debt coverage covenant (1.00x against 1.25x)"), the detail says what it means and names the document it was checked against. Ids live only in the evidence and metric links. On the overview each finding shows its kind as a label, is tidied client-side (no kind prefix, no mid-word cut, no raw decimals), and links to the claim, scenario, document, or report it concerns.

## 4. Deal Room (`/documents`)

- Upload zone (drag/drop + button), accepted types PDF/XLSX/CSV, 25 MB cap, 50 documents per deal, clear rejection reasons (extension, detected type, size, duplicate hash, archive budget, quota).
- Header sentence: "Add the seller's documents, let BearCase read them, then run analysis. Three questions below: what you uploaded, what we understood, and what is still missing." The drop zone names the documents to drop and says files are checked by content, never executed, and duplicates are rejected.
- **What you uploaded**: a table of Document (name, what was read from it in the reader's units: "12 pages read", "3 sheets, 214 rows read", and a "Technical details" disclosure holding hash, chunk count, classification confidence, and MIME), Type (plain names: "Sales memo (CIM)", "Financial statements", "Acquisition model", "Customer revenue file", "Loan term sheet", "Customer contract"; "Unsure; check the type" when classification confidence is low), Size (`fmtBytes`), Status (state machine *Uploaded → Queued → Parsing → Extracting → Ready* / *Failed*, glyph + label, a determinate progress bar while running, the failure reason when failed), and actions View and `Read again`.
- **What we understood**: the analysis summary for the deal (claims by status, the headline figures) or the running job.
- **What is missing**: the expected document types not yet present, in the order a buyer collects them, each with its one-line purpose (`DOC_PURPOSE`).
- Processing jobs: per-job step log with timestamps and a *Retry* action on failure.

**Document viewer** (drawer): header "Cited location: …" plus "highlighted parts are cited" when a citation opened it; a section filter when the document has several sheets or pages.

- Sheet evidence renders as one aligned table per sheet: the workbook's header row becomes the table header, every other row keeps its spreadsheet row number as a row header, numeric cells get thousands separators (`fmtCell`; four-digit years untouched; decimals kept as they came), cited rows are highlighted and carry a screen-reader "(cited)" marker, and a caption names the sheet, the row count, and how many rows are cited.
- CSV rows render as a definition list; money-like columns are formatted with separators.
- PDF paragraphs render as text blocks with their locator; instruction-like text keeps the *inert instruction text* badge (tooltip: shown but never followed), never hidden.
- The target row scrolls into view and is `aria-current`; Escape closes.

## 5. Claim Audit (`/claims`)

- Header sentence: "Every sentence the seller's documents present as a fact, checked against the other documents. Open a claim, read the evidence, then record what you decide."
- Toolbar: status filter chips (four, with counts), type filter, search, sort, keyboard hint (`J/K` move, `A` confirm, `C` correct, `R` reject, `E` evidence, `U` undo). Shortcuts fire anywhere on the page except inside text fields and open dialogs, and ignore any key pressed with a modifier.
- Split view: left, claim ledger rows — glyph+status, claim text (2 lines), type, claimed value (mono), verified value (mono, with Δ), confidence (5-segment meter with numeric label), source chip (`CIM p.3`). Right, the selected claim.
- Claim detail, top to bottom: the claim text with its source chip and extraction run (provider, model, prompt and schema versions); a line under the confidence meter, "Confidence is how confident the extractor was that this sentence is a claim. It is not a measure of whether the claim is true; the status below is."; four stats labelled **Seller says**, **Documents show**, **Difference**, **Rule applied**; the status explanation with inline citation chips and, for numeric claims, a "Calculation" disclosure that prints the formula and the input snapshot and says it was computed by the engine, never by the model; *Supporting* and *Contradicting* evidence cards (document, locator, quoted text or cells, *Jump to source*).
- **Your review** section: `Confirm assessment` (disabled once confirmed), `Correct…`, `Reject…`, `Undo` when a decision exists. Under the buttons: "Confirm records that you agree with the status *Contradicted* (the documents disagree with the seller's claim). Correct or reject when you disagree; each adds an entry under your name and the original AI output stays unchanged." A second row: `Jump to source`, `Ask about this claim` (opens the chat with the claim text, its status, and both numbers prefilled). Decision history in past tense ("confirmed the assessment", "rejected the finding", "corrected the claim", "undid the previous decision") with `fmtDateTime`.
- Reviewer dialog: opens in correct or reject mode from its own button or key; radio group with one line of guidance per mode; unit defaults to the claim's unit; a note is required. Toast titles: "Assessment confirmed", "Finding rejected", "Correction recorded"; description "Recorded as a separate entry. The original AI output is unchanged."; undo in the toast creates a superseding decision, never deletes.
- States: loading skeleton rows; empty ("No claims yet — process documents first" with link); partial (extraction running, ledger updates live); error with retry.

## 6. Financial Verification (`/financials`)

Header sentence: "The seller's adjusted EBITDA, rebuilt from the statements one adjustment at a time. Every number links to the cell or sentence it came from." Order on the page, top to bottom:

1. **What changed and why** — the seller's adjusted EBITDA (graphite), the verified figure (signal), the difference with a signed amount and percentage, reported EBITDA from the statements; one sentence counting accepted and excluded adjustments; a list of every excluded adjustment with its glyph and label, amount, decision, reason, evidence chips, and a Decide action. When nothing was excluded, a sentence says the verified number equals the seller's.
2. **Add-back bridge** (truncated axis, accessible table alternative) with the adjustments table: Adjustment, Amount, Decision, Why, Evidence, and per row `Decide…` and `Ask` (opens the chat with the adjustment, its amount, and the rule's decision). A line under the table says accepted adjustments are added back and the rest are excluded until a reviewer decides otherwise.
3. **Deal metrics** — cards with a one-line meaning each (CAGR, seller and verified adjusted EBITDA, enterprise value, EV and debt multiples, annual debt service, CFADS, DSCR, cash-on-cash, IRR, largest customer share, contract-supported recurring revenue), the source, a missing-inputs line, and a "Formula and inputs" disclosure.
4. **CFADS bridge** and **debt service coverage** side by side, each with a plain sentence (CFADS is the cash actually available to pay the lender; DSCR = CFADS ÷ annual debt service).
5. **Income statement, as mapped from the workbook** — introduced as the source data behind everything above; each cell is a citation chip to the sheet cell; calculated rows show their formula on hover.

Decision dialog: decisions use the status labels, the rationale field explains that it appears in the audit history and the report, and the rule-based decision stays in the audit trail.

## 7. Scenario Lab (`/scenarios`)

- Header sentence: "Test whether the business can still pay its loan when things go wrong. Change an assumption, run, and watch the debt coverage."
- **Sticky result strip** under the tabs (`role="status"`, `aria-live="polite"`): scenario name, year-one DSCR against the covenant with a breach or warning glyph and label, the draft state when assumptions are edited but not run, and `Run`. It stays on screen while the assumptions scroll.
- Left: assumption form (sliders + numeric inputs, both editable) with one plain sentence of help per field: revenue growth, largest-customer loss ("100% means the customer leaves entirely"), gross-margin change in bps ("100 bps is 1 percentage point"), labor and other opex growth, interest rate, purchase price, debt share, accepted add-backs, cash tax rate, maintenance capex, working capital. Unsaved edits are kept per scenario with a reset; a run saves them first.
- Right: results — KPI cards with notes (EBITDA after accepted add-backs; CFADS as cash available to pay the lender; debt service as interest plus principal; IRR as the annualized return, periodic not XIRR; break-even as the revenue at which the loan is just covered), the DSCR gauge with "Below 1.00x the business cannot pay its loan from its own cash", warnings, the five-year projection table, and the sensitivity grid with a sentence explaining rows (customer loss) and columns (margin change in bps; cells below the covenant are marked). Run history below.
- Scenario tabs: Base, Downside, Severe downside, + `New scenario`. A run persists an immutable result snapshot; earlier runs stay in the history.

## 8. Red-Team Report (`/report`)

- Left TOC (sticky) of 14 sections. Content column max-width 760px, Geist H2s, body Geist. Citation chips inline; hovering/focusing highlights the cited evidence in a side peek.
- Header: review outcome badge (one of four outcomes, never "buy/reject"), validation status ("All 47 material statements cited"), generated-at, prompt/schema/model versions, `Regenerate`, `Export Markdown`, `Export PDF`.
- Validation failures render as a blocking banner listing uncited statements; export disabled until resolved.
- Prose rules, enforced by a test: no raw ids in any statement or cell (objects are named; ids live in the citation lists), every number formatted for a reader by the shared engine formatter (separators, one decimal for percentages, two for multiples, none for money), and each section opening with a plain sentence that carries no figure, so intros never become material statements.
- Reading column capped at 76 characters. Grid `[180px, 1fr]` from lg and `[180px, 1fr, 260px]` from 2xl; the peek panel exists only at 2xl. Clicking any evidence chip opens the document at the cited location at every breakpoint; hover and focus drive the peek. A line under the header explains the chips: E opens the cited document at that spot, M marks a number computed by the engine, and a cited link shows where a statement came from, not that it is correct. Header shows the outcome with a glyph, the version, and `fmtDateTime`.

## 9. Audit history (`/audit`)

Header sentence: "Every change to this deal, who made it, and when. Reviewer decisions never overwrite the AI's original output; they are added here as separate entries." Table columns When, Who, What happened, Technical details. Every event code has a plain sentence ("Assessment confirmed", "Finding rejected", "Scenario run", "Document read again", "Report generated"); unknown codes fall back to the code in words. The filter groups by object: Deal, Documents, Claim reviews, Add-back decisions, Scenarios, Reports, Chat, Account. A line above the table names the viewer's time zone and every time uses `fmtDateTime`. Raw event names and payloads sit in the Technical details disclosure. Review decisions show original vs corrected values side by side.

## 10. Ask the deal (chat panel)

- Trigger: `⌘/` or `Ctrl+/` by platform, the floating button (bottom right), or a page action through the chat bus (`askTheDeal(text, { send })`: prefill and focus by default, send at once when asked; each hand-off is taken exactly once, and closing the panel discards a pending one). Hand-offs are plain user text: no markup, citations, or instructions.
- Panel: a right-side sheet, full width on mobile, `min(80vw, 880px)` on desktop. Header: "Ask the deal", a provider line ("Demo mode · rule-based answers", or "Live: Google Gemini · gemini-3.8-flash"), the model picker when a live provider offers several models, a "New conversation" button on mobile (the thread list is hidden there), the shortcut, and close. The panel resumes the last conversation for this deal in the session; closing it stops a running stream.
- Empty thread: "Ask anything.", the provider note from `chat/config`, and one paragraph: deal facts come from the ledger, metrics, decisions, runs, and documents, each with a citation you can open; a citation shows where a figure came from, not that the whole answer is right; everything else is answered as a general assistant. The connect-a-model panel appears when no key is present (free providers first, the `.env` line to add).
- Composer: textarea (Enter to send, Shift+Enter for a newline, grows to 160px), Send or Stop. Under it, whenever the assistant is idle, a `role="group"` "Quick prompts" row of small hairline chips (`--radius-1`, no pills): "Explain this finding" and "What should I ask the seller?" prefill the box and place the caret at the end; "What is missing?" and "What changed after this scenario?" send at once. Below: "Enter to send, Shift+Enter for a new line. Not financial, legal, tax, or investment advice."
- Replies: Markdown with citation chips inline; each evidence chip opens the source; a metric cited more than once gets one full chip and compact "same metric" markers after it (same tooltip, name for screen readers). Tool activity shows as labels while a reply streams.
- Footer per finished reply, glyph + label with a tooltip that explains it, one of: "All N citations resolve · review the answer" / "1 citation resolves · review the answer" / "No figures to cite · review the answer" (grounded deal reply; tooltip: every citation points at a passage or metric in this deal room, which shows where each figure came from, not that the whole answer is right); "Figures not cited from the deal room (n of m paragraphs cited)" (ungrounded; treat those figures as unverified); "General answer, not from the deal room" (general scope). Never "verified". Then provider and model, and the time. Copy and regenerate actions on each reply.

## Shared states

| State | Pattern |
|---|---|
| Loading | Skeleton with the exact final layout; never a spinner alone |
| Empty | Symbol + one sentence + one primary action |
| Partial | Live-updating with a mono "updating…" label and `aria-busy` |
| Success | Toast (4s, dismissible, focusable) |
| Error | Inline panel with cause, request id, `Retry`; never a bare red border. Copy is for the person using the product, never a developer command (`make api` belongs in the README, not in the UI); a 429 says too many requests and when to retry |

## Keyboard map

`⌘K` palette · `⌘/` chat · `J/K` next/prev row · `Enter` open · `Esc` close · `A` confirm · `C` correct · `R` reject · `E` jump to evidence · `U` undo · `[`/`]` prev/next section · `?` shortcut help. Single-letter shortcuts fire anywhere except inside text fields and open dialogs, and never with a modifier held.
