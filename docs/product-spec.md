# Product specification (as built)

See the package brief for the full original scope. This file records what shipped.

- Routes: `/`, `/demo`, `/methodology`, `/github`, `/app`, `/app/deals/new`, `/app/deals/[id]` (+ `documents`, `claims`, `financials`, `scenarios`, `report`, `audit`).
- Deal creation fields: company, industry, purchase price and basis, date, debt, equity, rate, amortization, covenant threshold (plus debt assumed / cash acquired for the equity-price basis).
- Inputs: PDF CIM, PDF term sheet, PDF contracts, XLSX statements, XLSX model, CSV customer revenue.
- Claim types: revenue, revenue growth, customer concentration, recurring revenue, churn, adjusted EBITDA, add-back, gross/operating margin, margin improvement, forecast, contract term, debt term, one-time expense.
- Statuses: supported, contradicted, unsupported, review required (+ pending before verification).
- Review actions: accept, reject (note required), correct (value/unit/status + note), undo. Add-back decisions with rationale.
- Scenarios: base, downside, severe downside, custom; twelve assumptions with ranges; immutable runs; sensitivity grid.
- Report: fourteen sections, four outcomes, validation, Markdown and PDF export.
- Optional features implemented: add-back waterfall, sensitivity matrix, downloadable report, one-click citation navigation, document viewer with inert-instruction labeling.
- Not implemented: reviewer comments UI (table exists), version comparison, claim graph, IC checklist, citation-first Q&A.
