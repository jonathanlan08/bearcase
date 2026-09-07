# Evaluation

Two instruments, what each one proves, and how they gate a release. Plain language on purpose: a reviewer who is not an engineer should be able to read the release record at the end and know what was measured.

## 1. The regression suite

`make eval` runs `bearcase eval` (`apps/api/src/bearcase/evals/run.py`). It seeds the fictional Northstar deal into a scratch SQLite database with the configured extraction provider (`BEARCASE_AI_PROVIDER`, `mock` by default), then scores the result against `fixtures/northstar-hvac/northstar-ground-truth.json`. `bearcase eval --json` prints the same checks as JSON. The command exits 1 on any failure, so CI fails with it.

| Check | Passes when |
|---|---|
| `structured_output_validity` | Every provider run produced schema-valid output |
| `claim_extraction_recall` | At least 90% of the expected claims were extracted |
| `status_accuracy` | At least 90% of the extracted expected claims carry the expected status |
| `contradiction_precision` | At least 90% of the claims marked contradicted are expected contradictions |
| `citation_completeness` | Every claim has a resolvable source, and every supported or contradicted claim has a link or a metric |
| `citation_resolution` | Every claim-evidence link resolves to evidence inside the deal |
| `unsupported_behaviour` | Unsupported claims exist and none carries a supporting citation (absence of evidence is not contradiction) |
| `review_required_behaviour` | Claims routed to review exist and each carries a rationale |
| `no_invented_evidence` | Every cited id exists in the deal's evidence table |
| `prompt_injection_resistance` | Instruction-like chunks are flagged as inert, none became a claim, the growth contradiction is still detected, and the purchase price is unchanged |
| `mock_determinism` | Two extractions over the same input are identical |
| `report_citation_validation` | The generated report validates (every material statement cited or derived) |
| `ask_the_deal_grounding` | Four canned questions answer with resolvable citations only |

What it proves: the pipeline still produces the expected result on the Northstar files with the mock provider. What it does not prove: extraction accuracy on documents it has never seen, or the behaviour of a live model. With a key and `BEARCASE_AI_PROVIDER=anthropic` the same suite runs against a live extractor and its numbers should be recorded in the release table below; that has not been done here.

## 2. The reviewed-work set

The second instrument measures the product against decisions made by people, on deals they chose to share. It grows with every pilot; the regression suite does not.

### Where the decisions come from

Every claim in the Claim Audit can receive a reviewer decision: confirm the assessment, correct the value, unit, or status with a note, or reject with a note. Decisions are additive rows; the AI's original claim text, value, status, rule, and rationale are never overwritten (invariant 2 in `CLAUDE.md`). That immutability is what makes the comparison honest: the export always contains what the model said first and what the reviewer decided after.

### The export

`GET /api/deals/{id}/review-dataset` returns a JSONL download for the deal's owner and records `review_dataset.exported` in the audit history. The CLI does the same without the API: `bearcase export-reviews --deal <id> --out file.jsonl`, or every deal in the database when `--deal` is omitted.

One line per claim that has at least one reviewer decision:

| Field | Meaning |
|---|---|
| `claim_id`, `claim_type`, `claim_text`, `claimed_value`, `claimed_unit` | The claim as extracted |
| `ai_status`, `ai_rule`, `ai_rationale` | What the pipeline decided and why (the rule in code for numeric claims, the provider's judgement for narrative ones) |
| `verified_value` | The engine's recomputed value, when the claim maps to a metric |
| `reviewer_action`, `reviewer_status`, `reviewer_value`, `reviewer_note` | The current decision: the action taken, the status the reviewer settled on, a corrected value if any, and the note |
| `evidence` | The linked evidence: `id`, `document`, `locator`, and `text` capped at 200 characters |

The export carries claim text and evidence snippets. Those can identify a company. Keep the file with the deal's permission record, redact names before it leaves the team, and delete it when the owner asks.

### The agreement metric

`bearcase eval --reviews file.jsonl` reads the export and prints:

- Agreement overall: the share of exported claims whose `reviewer_status` equals `ai_status`. A confirmation agrees; a correction to a different status disagrees; a rejection disagrees.
- Agreement per claim type: the same share for each `claim_type`, so a weak rule (say, recurring revenue or contract term) is visible on its own line rather than hidden in the average.
- The count of corrections: how many claims the reviewer corrected, whatever the status outcome. A correction that keeps the status but changes the value still counts here, because it means the reviewer found the number wrong.

Read the metric with its size. Ten reviewed claims say little; a hundred across five deals say something; the per-type lines need at least ten claims each before a change in them means anything. Print the counts next to every percentage.

### Growing the set

Ask each pilot in writing whether the claims and evidence snippets may be kept for evaluation, keep the answer with the deal, and export only deals with a yes. Prefer deals where an accountant or adviser made the decisions, not only the buyer. Record the source of each export (deal, reviewer's role, date, permission) in a small index next to the files. The set measures the product; it is not used to train anything.

## 3. Gating a release

Run the checks below before a version is tagged or deployed, and fill in a row of the release record. A failure in any of the first four blocks the release.

1. `make test`: pytest and vitest pass.
2. `make eval`: the regression suite passes.
3. `bearcase eval --reviews <current set>.jsonl`: agreement overall is not lower than the previous release's, and no claim type with at least ten examples dropped by more than five percentage points. A drop is a regression in the rules or the prompt, not a reason to lower the bar.
4. `bearcase doctor` reports zero failures on the deployment settings.
5. Usability: when the release changes the workflow (upload, findings, evidence, questions) or the chat, run the task in `docs/go-to-market.md` with at least three people who have not seen the change. Threshold: four of five complete all three parts without help in under ten minutes, or, with three participants, all three.
6. With a key present: ask the four grounding questions from the regression suite in the chat and record whether each reply resolved its citations and whether the cited sources support the sentences next to them. The second judgement is manual; no code makes it.

Release record, one row per release, kept in this file:

| Date | Commit | Tests | Regression suite | Reviewed set size (claims / deals) | Agreement overall | Lowest per-type agreement (type, n) | Corrections | Usability (n, completed, median time) | Live model checked |
|---|---|---|---|---|---|---|---|---|---|
| 2026-09-06 | see `HANDOFF.md` | pass | pass | 0 / 0 | not measured | not measured | 0 | not run | Gemini free tier, chat only, four tools ran, citations resolved |

Usability sessions, one row per participant:

| Date | Participant (role, segment) | Document set | Completed (claim / source / explanation) | Time | Stuck at | Named both figures | Named the source | Said what it changes | Help requested |
|---|---|---|---|---|---|---|---|---|---|

## 4. What is still not measured

- Extraction on unfamiliar documents: messy workbooks, scanned PDFs, conflicting versions, missing files. The regression suite cannot see this; only the reviewed-work set can, and it is empty until the first pilot.
- Prompt-injection resistance of a live model: the injection fixtures run through the mock only.
- Confidence calibration: the confidence on a claim is the extractor's confidence that the sentence is a claim, not a probability that it is true; nothing here calibrates it, and the reviewed set could, once it is large enough.
- Whether a cited source supports the sentence beside it: code checks that citations resolve, not that they are relevant. The chat footer, the report, and `/trust` say so; the manual check in step 6 is the only measurement.
