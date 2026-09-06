# HANDOFF

Last updated: 2026-09-06. Single-session build with Claude Fable 5.1 (no subagents were required; see "Agent organization" below).

## State

| Phase | Status |
|---|---|
| 0 Recovery and planning | done — design docs (10), architecture, data model, trust boundary, implementation plan |
| 1 Foundation | done — monorepo, FastAPI + SQLAlchemy + Alembic (1 migration), Next.js 16 app, CI, Docker |
| 2 Synthetic data and engine | done — `northstar_facts.py` single source of truth, generator, ground truth, 16 formulas, scenario engine, tests with hand-checked values |
| 3 Processing and AI pipeline | done — validation, parsers, classification, evidence, mock + Anthropic providers, retrieval, guardrails, injection detection |
| 4 Claim Audit and Financial Verification | done — extraction, deterministic verification, add-back review, review decisions, audit events, UI |
| 5 Scenario Lab and report | done — immutable runs, sensitivity grid, report assembly, citation validation, MD/PDF export, UI |
| 5b Ask the deal | done — streaming chat (`chat_threads`, `chat_messages`, migration 3) with a tool-use loop over persisted rows for Anthropic and any OpenAI-compatible provider (`chat/providers.py` resolves the backend from keys in `.env`; `chat/openai_compat.py` runs the loop for Gemini, Groq, OpenRouter, Ollama, OpenAI, custom), a grounded no-tools fallback for models without tool calling, actionable provider errors with key redaction, and the rule-based composer when no key is present; the chat panel lists connectable providers free-first; single-shot Q&A endpoint retained |
| 6c Scene realism | done — transmission glass core with lit interior, paper with thickness and shading, procedural environment and contact shadows, soft additive particles, bloom and vignette by tier, camera dolly; both waterfall charts rebuilt as truncated-axis bridges |
| 6b Design pass | done — removed serif display, eyebrows, section numbers, dot strips; one radius scale; landing sections use five distinct layouts; impeccable detector reports 0 findings |
| 6 Landing page and polish | done — Ink/Paper design, Evidence Core scene with static fallback, methodology page |
| 7 Audit and GitHub readiness | see "Verification" |

## Verification (run on this machine, 2026-09-06)

| Check | Result |
|---|---|
| `pytest` (apps/api) | 85 passed (40 cover chat backend resolution, the OpenAI-compatible loop with fake clients, the no-tools fallback, error mapping, and key non-disclosure) |
| `bearcase eval` (mock provider) | PASS, 12/12 checks (incl. Ask the Deal grounding); extraction recall 19/19; status accuracy 19/19; contradiction precision 6/6; 65/65 citations resolve; report v1 valid (36/36 material statements cited) |
| `ruff check` / `ruff format --check` / `mypy src` | clean |
| `vitest` (apps/web) | 11 passed |
| `tsc --noEmit` / `eslint` | clean |
| `next build` | success (15 routes) |
| Playwright smoke (chromium + mobile) | 6 passed |
| Browser console on landing and app pages | no errors (only Three.js deprecation warnings from dependencies) |
| Screenshots | `docs/screenshots/01-13` captured from the running stack |

No live model was exercised with a real key (none in this environment). The Anthropic provider is implemented per the SDK docs; the OpenAI-compatible loop is covered by fake-client tests (split tool-call deltas, Gemini extra-field echo, Ollama-style repeated indexes, usage-only chunks, the no-tools fallback, error mapping) and one real request to Gemini's OpenAI-compatible endpoint with an invalid key, which confirmed the auth-error path and that the key never appears in the SSE stream or the log. Both providers share all guardrails with the mock. Docker Compose was written but not run (no Docker on this machine).

## Decisions that differ from the original package (deliberate)

1. **Zero-infrastructure default.** SQLite + local storage + in-process job runner so a clean checkout runs with `make seed && make dev`. PostgreSQL, S3/MinIO, and a polling worker are config switches (Docker Compose shows the full shape). Reason: the dev machine had no Docker; a portfolio demo must actually run.
2. **No pgvector.** The corpus is small and verification needs exact lexical/numeric overlap; a BM25 retriever sits behind a `Retriever` protocol.
3. **Numeric claims are settled by code, not the model**, in both providers. The model only judges narrative claims and drafts prose.
4. **Add-back review is rule-based against statement lines** (recurrence, prior-year excess, missing line) with human override that recomputes verified EBITDA.
5. **The mock provider is a real rule-based extractor** over document text, not canned output; the same fixtures exercise the real parsing path.

## File ownership

Single author this session. Suggested partition for future parallel work: `engine/` + `fixtures/` (finance), `ingest/` + `ai/` + `pipeline/` (platform), `apps/web/src/components/scene` (3D), everything else (product).

## Resume steps

1. `git status`; read this file and `CLAUDE.md`.
2. `make setup && make seed && make test && make eval`.
3. `make dev`, open `/demo`, walk the five sections.
4. Next candidates: connect a free provider (`GEMINI_API_KEY` or `GROQ_API_KEY` in `.env`) and record live chat grounding numbers; reviewer comments UI (model exists); document version comparison; Anthropic-mode extraction run with recorded eval numbers; Lighthouse pass on the landing page.
