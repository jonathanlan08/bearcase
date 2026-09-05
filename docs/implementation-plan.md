# Implementation plan (retrospective)

Order of work and gates, as executed in one session:

1. Design docs (`docs/design/`) from the UI/UX Pro Max search plus hand refinement; palette validated with the dataviz validator (light passes all checks).
2. API foundation: settings, SQLAlchemy models, enums, Alembic.
3. Engine: formulas → scenarios → metrics; Northstar facts with assertions; fixture generator; ground truth.
4. Ingest: validation, storage, parsers, classification, statement mapper, customer aggregation, injection detector.
5. AI: schemas, prompts, provider protocol, mock provider, Anthropic provider, retrieval, guardrails.
6. Pipeline: jobs, process_document, analyze (metrics, adjustments, claims, verification, findings, scenarios), report assembly/validation/export.
7. API routes, auth, seed, CLI, tests, evaluation harness.
8. Web: tokens, shell, seven views, viewer, review dialog, charts, landing page, scene, methodology.
9. CI, Docker, docs, handoff.

Gate results are recorded in `HANDOFF.md`.
