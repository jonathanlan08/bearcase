# Data model

Twenty-two tables (the twenty-one required plus `user_sessions`). UUID primary keys, timezone-aware timestamps, `Numeric(20,2)` money and `Numeric(20,8)` ratios, JSON for snapshots and locators, explicit string enums.

```
users ─┬─ user_sessions
       └─ deals ─┬─ documents ── document_versions
                 ├─ processing_jobs
                 ├─ extraction_runs
                 ├─ evidence (document, version, kind, chunk_index, locator, text, structured, contains_instruction_text)
                 ├─ claims ─┬─ claim_evidence_links (role: source | supporting | contradicting)
                 │          └─ review_decisions (additive; supersedes_id; is_current)
                 ├─ findings
                 ├─ financial_periods ── financial_metrics (source: extracted | calculated | verified | scenario; formula; input_snapshot; evidence_ids)
                 ├─ adjustments
                 ├─ scenarios ─┬─ scenario_assumptions
                 │             └─ scenario_results (immutable: input_snapshot, outputs, warnings, input_hash, engine_version)
                 ├─ reports ── report_citations (evidence | calculation; resolved)
                 ├─ reviewer_comments
                 └─ audit_events
```

## Invariants

- `Claim.claim_text`, `claimed_value`, `status`, `status_rationale` are written by the pipeline and never by review endpoints; reviews create `ReviewDecision` rows and the API derives `effective_status`.
- `ScenarioResult` rows are never updated; `run_no` increments per scenario.
- `FinancialMetric.evidence_ids` are unique and resolvable; `input_snapshot` contains the `Calc` snapshot (inputs, formula, missing, notes).
- `Evidence.locator` carries `page/paragraph/bbox`, `sheet/row/range`, `row/record_index`, or `aggregate/rows`.
- State machines: `DocumentStatus` (uploaded → queued → parsing → extracting → ready | failed), `JobStatus`, `ClaimStatus`, `AdjustmentDecision`, `ReportStatus`, `FindingStatus`.
- All deal-owned tables carry `deal_id` with `ON DELETE CASCADE`; access is checked through `deals.owner_id`.

Migrations: `apps/api/alembic/versions/`. The API applies migrations at startup outside production; use `bearcase migrate` in production.
