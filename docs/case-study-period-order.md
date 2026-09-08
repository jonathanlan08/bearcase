# Case study: reversing the spreadsheet columns reversed the growth rate

A real defect found in BearCase on September 7, 2026 by an outside review, how it changed the answer, how it was fixed, and the regression test that now guards it. Written for anyone judging the engineering behind the product, including interviewers.

## The defect

BearCase reads a seller's income statement from a spreadsheet, maps each row to a canonical line (revenue, cost of goods sold, EBITDA, and so on), and recomputes ratios such as annual growth. The mapper kept the year columns in the order they appeared in the sheet, and the growth engine assumed that order was oldest to newest and that the number of columns minus one was the number of years elapsed.

Three small synthetic statements for the same business, all with revenue of 100, 110, and 121 over FY2022 to FY2024, produced three different answers:

| Layout | Correct annual growth | BearCase said |
|---|---:|---:|
| Columns FY2022, FY2023, FY2024 | 10% | 10% |
| Columns FY2024, FY2023, FY2022 | 10% | −9.1%, attributed to FY2022 |
| Columns FY2022 and FY2024 only | 10% | 21% |

The existing test suite, 219 tests at the time, passed throughout, because every fixture used the ascending three-column layout. Nothing was wrong with the arithmetic. The interpretation of the input was wrong, and the product's polish made the wrong number easy to trust.

Two related interpretation gaps were found in the same pass. A sheet titled "USD in thousands" was read as raw dollars, so 1,210 stayed 1,210 instead of becoming 1,210,000. And a statement with "Revenue - service" and "Revenue - installation" rows and no total row kept whichever component row came first as the revenue figure.

## Why it mattered

The product's promise is checking a seller's numbers against the seller's own documents. A statement that happens to list the most recent year first is common. On such a statement BearCase would have reported a shrinking business as growing, or a growing one as shrinking, with a citation to the exact cell, which is worse than no answer because it looks verified.

## The fix

Three changes in `apps/api/src/bearcase/ingest/statement_mapper.py` and `apps/api/src/bearcase/engine/metrics.py`:

1. **Periods are sorted by the year in their label** before anything is mapped. Column order no longer matters, and two columns naming the same year reject the sheet rather than mapping it.
2. **Elapsed time comes from the years, not the column count.** FY2022 to FY2024 is two years whether or not FY2023 is present. A growth figure computed across a gap carries a note ("spans 2 years, not one; review required") that the financial screen shows.
3. **Scale and components are read, not assumed.** "In thousands", "$000s", and "in millions" in a sheet title multiply every value, with the raw cell kept beside the scaled one. Component rows with no total are summed, given a low confidence, flagged for review, and listed by name in a new "Check what we read" panel, so a person confirms the sum before trusting it.

## The regression test

`apps/api/tests/test_statement_layouts.py` builds the three equivalent layouts directly against the mapper and the engine, with no database, and asserts they produce the same periods, the same growth, and the same attribution. It also covers the duplicate-year rejection, the thousands and millions scales, the sheet-title scale, the component sum, the total-row-wins rule, and a title containing a number that must not be mistaken for a scale. Eight tests, under a second.

The Northstar ground-truth fixtures were unchanged by the fix, and the full suite stayed green, which is what a fix to input interpretation should look like: the correct cases keep their answers, and the previously silent cases now either give the right answer or stop for review.

## What it taught

- A passing suite measures the cases someone thought to write. The failure here was a missing family of cases, equivalent inputs in different layouts, not a wrong assertion.
- Deterministic arithmetic is necessary and not sufficient. The product now separates "calculated from imported figures" from "confirmed by a person", and shows the interpretation (years, scale, rows) before the results that depend on it.
- The right response to an ambiguous input is to stop and ask, and to say so in the interface, rather than to produce a confident-looking number.
