# Feature proposals

Implemented (three discretionary features plus small additions):

1. **Add-back waterfall** — user problem: seeing which seller adjustments survive review and why. Demo value: the $2.10M → $1.81M story in one figure. Approach: engine-computed steps in the financials endpoint; SVG chart with hatched exclusions and a table alternative. DB impact: none. Security: none. Tests: API assertions on running totals.
2. **DSCR sensitivity matrix** — problem: one downside case is not enough to see where the deal breaks. Approach: `sensitivity_grid` recomputes year-1 DSCR over two assumptions; grid cells carry a breach glyph. DB: none (computed on demand). Tests: engine and API.
3. **Downloadable report** — problem: the review has to leave the tool. Approach: Markdown and PDF (reportlab) export of a validated report only. DB: none. Security: export disabled unless validated.

Deferred with reasons: reviewer comments (table exists; UI not needed for the demo narrative), version comparison (needs a second fixture set), claim graph (spectacle risk), IC checklist (would duplicate the report's missing-information section), citation-first Q&A (secondary to the structured workflow).
