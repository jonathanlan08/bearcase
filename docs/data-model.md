# Data model

Twenty-five tables (the twenty-one required plus `user_sessions`, `auth_tokens`, `deal_members`, and `purchases`). UUID primary keys, timezone-aware timestamps, `Numeric(20,2)` money and `Numeric(20,8)` ratios, JSON for snapshots and locators, explicit string enums.

```
users ─┬─ user_sessions
       ├─ auth_tokens (purpose: verify | reset | invite; token_hash; expires_at; used_at; payload)
       ├─ purchases (kind: pilot; amount_cents; currency; status: pending | paid | failed; stripe_session_id; stripe_payment_intent; deal_id)
       └─ deals ─┬─ deal_members (user_id, nullable until accepted; invited_email; role: viewer | editor; invited_by; accepted_at)
                 ├─ documents ── document_versions
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
- All deal-owned tables carry `deal_id` with `ON DELETE CASCADE`; access is checked through `deals.owner_id` or an accepted `deal_members` row (`user_id` set, `accepted_at` set), and the member's role decides what they may write.
- `users.email_verified_at` is null until the account's verification token is used; sharing a deal requires it.
- `auth_tokens` never stores the token itself, only `token_hash` (SHA-256 of a random urlsafe token). A token is single use (`used_at`) and expires (`expires_at`): 24 hours for `verify`, 1 hour for `reset`, and the invite's own expiry. `payload` carries what the purpose needs (the invite's deal and role). A `reset` token that is used revokes every `user_sessions` row of that user.
- `deal_members` holds at most five rows per deal; `user_id` stays null until the invited address accepts through a signed-in account whose email matches the `invited_email` case-insensitively. Roles: `editor` may do everything but delete the deal, manage members, or export the review dataset; `viewer` may read, chat, and export seller questions but not upload, delete documents, run analysis, record decisions, or run scenarios. Audit events record a member's actions under the member's own `user_id`.
- `purchases` is written by the billing routes only: a row is `pending` when a Stripe Checkout Session is created (`stripe_session_id` unique) and becomes `paid` with `paid_at` and `stripe_payment_intent` when the signed `checkout.session.completed` webhook arrives; a repeated webhook for the same session changes nothing. Amounts are integers in the smallest currency unit.

Migrations: `apps/api/alembic/versions/`. The API applies migrations at startup outside production; use `bearcase migrate` in production.
