# AI trust boundary

## Model responsibilities
Classification (only when rules cannot decide), material-claim extraction with a source chunk index, evidence-role judgement for narrative claims, contradiction suggestions, unsupported-assumption identification, management-question and negotiation-condition drafting, narrative sections, explanation of persisted calculations.

## Deterministic code responsibilities
File validation and hashing; auth and per-deal authorization; state transitions; statement mapping; every financial formula and scenario; citation resolution; numeric claim verification with tolerances; add-back review rules; report validation; audit history.

## Rules enforced in code
1. Document text reaches the model only inside `<document>` tags with a system rule that it is data. Instruction-like text is flagged (`ingest/injection.py`), stored inert, and reported as a `document_integrity` finding.
2. Provider output must validate against `schemas/ai_v1.py` (`extra="forbid"`); invalid output is retried once, then recorded as `invalid_output` and the step degrades safely (claim dropped or routed to review).
3. A claim whose `source_chunk_index` does not resolve is discarded rather than persisted with an invented source.
4. Guardrails (`ai/guardrails.py`): Supported requires ≥1 supporting citation; Contradicted requires ≥1 contradicting citation; no citations → Unsupported; confidence < 0.6 or mixed evidence → Review required.
5. Numeric claims with an engine metric are decided by comparison in code (`pipeline/analyze.py::_compare`), never by the model. Tolerances: 1.0 percentage point, 2% for currency, 0.05 for multiples.
6. Only primary sources (statements, customer file, contracts, term sheet) can support or contradict; the seller's narrative documents never corroborate each other.
7. Original AI output is immutable. Human decisions are additive and audited.
8. Prompt version, schema version, model, provider, usage, and input hash are stored on every `ExtractionRun` and on every `Report`.
9. Missing evidence is stated, never invented. Absence of evidence yields Unsupported, not Contradicted.
10. Every demo surface discloses synthetic data and non-advice status.

## Ask the Deal
Questions are answered only from persisted rows (claims, metrics, adjustments, scenario results, findings, evidence). Code builds the material and validates the answer; the model (or the rule-based composer) only drafts sentences. Sentences with numbers that lack a resolvable citation are removed and the answer is marked not fully grounded. No new calculations are performed while answering.

## Evaluations
`bearcase eval` seeds Northstar into a scratch database and scores: structured-output validity, extraction recall, status accuracy, contradiction precision, citation completeness, citation resolution, unsupported behaviour, review-required behaviour, no invented evidence, prompt-injection resistance, mock determinism, report citation validation, Ask the Deal grounding.
