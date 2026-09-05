# Application Specification (`/app/...`)

World: **Paper** (default), dark option. The app is a ledger: dense, calm, keyboard-first, provenance always one action away.

## Route map

| Route | View | Primary object |
|---|---|---|
| `/app` | Deal list + recent activity | Deals |
| `/app/deals/new` | Create deal form | Deal |
| `/app/deals/[dealId]` | Deal overview | Deal summary, status ring, findings digest |
| `/app/deals/[dealId]/documents` | **Deal Room** | Documents, processing jobs |
| `/app/deals/[dealId]/claims` | **Claim Audit** | Claim ledger, evidence split view |
| `/app/deals/[dealId]/financials` | **Financial Verification** | Periods, metrics, add-back waterfall |
| `/app/deals/[dealId]/scenarios` | **Scenario Lab** | Scenario assumptions, results, sensitivity |
| `/app/deals/[dealId]/report` | **Red-Team Report** | Report sections, citations, export |
| `/app/deals/[dealId]/audit` | Audit history | Review decisions, audit events |

## Shell

- **Desktop (≥1024px):** 232px left rail (collapsible to 56px icon rail; state persisted). Rail: wordmark, deal switcher, five primary nav items with `01–05` mono prefixes, then `Overview` and `Audit history` as secondary, then mode badge (`MOCK AI` / `ANTHROPIC`) and the fictional-data notice.
- **Tablet:** rail collapsed to icons; labels on hover/focus and in a tooltip.
- **Mobile (<768px):** top bar (deal name, overflow menu) + bottom tab bar with the five primary items (icons + labels, 56px tall, safe-area padded).
- **Page header:** H1 (serif), deal micro-label (`NORTHSTAR HVAC · FICTIONAL`), right-aligned actions.
- **Command palette:** `⌘K` — jump to claim, document, section; run "Process documents", "Generate report".

## 1. Deal list (`/app`)

Table: Deal, Industry, Purchase price (mono), Documents (n processed/n), Claims (status counts as four mini glyphs), Updated. Row click opens overview. Empty state: Evidence Link symbol, "No deals yet", buttons `Open the Northstar demo` and `Create a deal`. Right column: recent audit events (last 10).

## 2. Create deal (`/app/deals/new`)

Single-column form, labels above inputs, helper text below. Fields: Company name, Industry, Purchase price, Purchase-price basis (radio: *Enterprise value* / *Equity price*), Purchase date, Debt amount, Equity amount, Interest rate (%), Amortization (years), Covenant DSCR threshold (optional, default 1.25). Inline validation on blur; error summary at top on submit failure with links to fields. Live derived line: "Debt/(Debt+Equity) = 60.0%".

## 3. Deal overview

Grid: (a) verification summary — four status counts as a segmented bar with glyphs; (b) seller vs verified adjusted EBITDA (two-bar mini); (c) DSCR by scenario with threshold rule; (d) missing information checklist; (e) next action. Each card links into its section.

## 4. Deal Room (`/documents`)

- Upload zone (drag/drop + button), accepted types PDF/XLSX/CSV, 25 MB cap, clear rejection reasons (extension, detected type, size, duplicate hash).
- Document table: Name, Type (classified), Pages/Sheets/Rows, Status (state machine: *Uploaded → Queued → Parsing → Extracting → Ready* / *Failed*), Hash (short), Actions (view, reprocess). Status uses glyph + label + a determinate progress bar while running.
- Processing drawer: per-job step log with timestamps and a *Retry* action on failure.
- Document viewer (drawer or route panel): page list / sheet grid / CSV rows with the evidence chunk boundaries outlined; selecting a chunk shows which claims cite it. Instruction-like text is shown with an *inert instruction text* badge, never hidden.

## 5. Claim Audit (`/claims`)

- Toolbar: status filter chips (four, with counts), type filter, search, sort, keyboard hint (`J/K` move, `Enter` open, `A/R/C` accept/reject/correct, `E` jump to evidence).
- Split view: left, claim ledger rows — glyph+status, claim text (2 lines), type, claimed value (mono), verified value (mono, with Δ), confidence (5-segment meter with numeric label), source chip (`CIM p.3`). Right, evidence panel for the selected claim: *Supporting* and *Contradicting* lists; each evidence card shows document, locator (`page 3 ¶2` / `Sheet IS!C7` / `row 14`), the quoted text or cells, and a *Jump to source* action which opens the document viewer scrolled to the locator.
- Status explanation block: rationale text with inline citation chips; "How this status was decided" disclosure listing the rule applied (e.g., *numeric mismatch beyond 2.0% tolerance*).
- Review controls: `Accept`, `Reject`, `Correct…` (opens a dialog: corrected value/unit/note). Original AI output stays rendered above the human decision with a "Original extraction (immutable)" label. Decisions post an audit event and show a toast with undo (undo creates a superseding decision, never deletes).
- States: loading skeleton rows; empty ("No claims yet — process documents first" with link); partial (extraction running, ledger updates live); error with retry.

## 6. Financial Verification (`/financials`)

- Period table: FY2022–FY2024 columns; rows revenue, COGS, gross profit, opex lines, EBITDA, D&A, interest, tax, net income. Each cell is a citation chip to the sheet cell. Extracted (mono) vs mapped confidence indicator per row.
- Metric cards: revenue growth per year + CAGR, gross margin, operating margin, reported EBITDA reconciliation (expandable bridge), verified adjusted EBITDA, EV/EBITDA (seller vs verified), Debt/EBITDA, annual debt service, CFADS bridge (expandable), DSCR, cash-on-cash, IRR with method note.
- Add-back waterfall: seller adjustments table with decision column (Accepted / Rejected / Review / Unsupported), evidence chip, and the waterfall chart (accessible table alternative toggle).
- Every card has a "Formula" disclosure that prints the formula and the input snapshot with citations.

## 7. Scenario Lab (`/scenarios`)

- Scenario tabs: Base, Downside, Severe downside, + `New scenario`.
- Left: assumption form (sliders + numeric inputs, both editable): revenue growth %, largest-customer loss %, gross-margin change (bps), labor cost growth %, interest rate %, purchase price, debt %, accepted add-backs (checkbox list). Labels always visible; units in suffix.
- Right: results — revenue, EBITDA, CFADS bridge, annual debt service, DSCR (with threshold rule and warning glyph), cash-on-cash, IRR, warnings list. A "Run scenario" button persists an immutable result snapshot; unsaved edits show a *draft* badge. Snapshot history list below.
- Sensitivity matrix: DSCR grid (customer loss × margin compression), cells carry value text and a breach glyph; color is secondary.

## 8. Red-Team Report (`/report`)

- Left TOC (sticky) of 14 sections. Content column max-width 760px, serif H2s, body Geist. Citation chips inline; hovering/focusing highlights the cited evidence in a side peek.
- Header: review outcome badge (one of four outcomes, never "buy/reject"), validation status ("All 47 material statements cited"), generated-at, prompt/schema/model versions, `Regenerate`, `Export Markdown`, `Export PDF`.
- Validation failures render as a blocking banner listing uncited statements; export disabled until resolved.

## 9. Audit history (`/audit`)

Timeline table: time, actor, event type, object, summary, diff disclosure. Filter by type. Review decisions show original vs corrected values side by side.

## Shared states

| State | Pattern |
|---|---|
| Loading | Skeleton with the exact final layout; never a spinner alone |
| Empty | Symbol + one sentence + one primary action |
| Partial | Live-updating with a mono "updating…" label and `aria-busy` |
| Success | Toast (4s, dismissible, focusable) |
| Error | Inline panel with cause, request id, `Retry`; never a bare red border |

## Keyboard map

`⌘K` palette · `J/K` next/prev row · `Enter` open · `Esc` close · `A/R/C` review actions · `E` jump to evidence · `[`/`]` prev/next section · `?` shortcut help.
