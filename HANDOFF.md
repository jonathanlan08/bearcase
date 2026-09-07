# HANDOFF

Last updated: 2026-09-06 (evening). Built with Claude Fable 5.1. Phases 0 to 6 were a single session; phase 7 ran as a lead plus parallel agents, each owning a file set (see "File ownership").

## State

| Phase | Status |
|---|---|
| 0 Recovery and planning | done — design docs (10), architecture, data model, trust boundary, implementation plan |
| 1 Foundation | done — monorepo, FastAPI + SQLAlchemy + Alembic (1 migration), Next.js 16 app, CI, Docker |
| 2 Synthetic data and engine | done — `northstar_facts.py` single source of truth, generator, ground truth, 16 formulas, scenario engine, tests with hand-checked values |
| 3 Processing and AI pipeline | done — validation, parsers, classification, evidence, mock + Anthropic providers, retrieval, guardrails, injection detection |
| 4 Claim Audit and Financial Verification | done — extraction, deterministic verification, add-back review, review decisions, audit events, UI |
| 5 Scenario Lab and report | done — immutable runs, sensitivity grid, report assembly, citation validation, MD/PDF export, UI |
| 5b Ask the deal | done — streaming chat (`chat_threads`, `chat_messages`, migration 3) with a tool-use loop over persisted rows for Anthropic and any OpenAI-compatible provider (`chat/providers.py` resolves the backend from keys in `.env`; `chat/openai_compat.py` runs the loop for Gemini, Groq, OpenRouter, Ollama, OpenAI, custom), a grounded no-tools fallback for models without tool calling, actionable provider errors with key redaction, and the rule-based composer when no key is present. The assistant is general-purpose and also knows the deal: general questions are answered in Markdown (rendered with citation chips inline); deal facts come only from the eight tools and carry `[E:…]`/`[M:…]` markers checked in code; `stream_reply` labels every reply with a scope (`deal` when a citation resolved or a tool ran, else `general`) stored in the citations payload and sent in the `citations` and `done` events; `POST /chat` accepts an optional `model` (regex-validated, 400 otherwise, applied only when the backend is live, recorded on the rows) and `GET /chat/config` returns a per-provider `models` list; the panel has a model picker when live, copy and regenerate actions, and a scope label in the footer. Live models remain unverified end to end here (no key) |
| 6c Scene realism | done — transmission glass core with lit interior, paper with thickness and shading, procedural environment and contact shadows, soft additive particles, bloom and vignette by tier, camera dolly; both waterfall charts rebuilt as truncated-axis bridges |
| 6b Design pass | done — removed serif display, eyebrows, section numbers, dot strips; one radius scale; landing sections use five distinct layouts; impeccable detector reports 0 findings |
| 6 Landing page and polish | done — Ink/Paper design, Evidence Core scene with static fallback, methodology page |
| 7 Astra review response | done — an independent review (`bearcase.ai astra rewrite/audit/REVIEW.md`, untracked, read-only) was answered item by item in `docs/astra-review-response.md`. Adopted: per-visitor demo isolation with 14-day retention and legacy shared sessions retired; bounded upload reads, an XLSX archive budget, storage quotas (50 documents per deal, 500 MB per user), and a per-user token-bucket rate limit on demo start, upload, reprocess, process, chat, and ask (`api/ratelimit.py`); `P&L` sheet aliases in the statement mapper; the stray `fmtValue` page export removed; findings rewritten for the buyer with one engine formatter for every reader-facing number; overview start section with a plain next step and a two-term glossary; claim page with "Confirm assessment", "Seller says / Documents show", a confidence explanation, and "Ask about this claim"; citation viewer as one aligned table per sheet with separators; financials led by "What changed and why"; scenario lab with a sticky result strip and per-assumption help; chat panel at `min(80vw, 880px)` with four quick prompts, claim context through `lib/chat-bus.ts`, and "same metric" markers; the hero told in three chapters (seller says 18%, statements show 11.6%, open the evidence) with visible captions and a pause control; landing page framing section with the four-step first session and "Open your workspace"; methodology retitled "How we check claims" with "What a citation means"; honest citation wording (provenance, not truth; a deal reply needs at least one resolved citation to be grounded; the fictional-data note goes into the prompt only for demo deals); README, SECURITY, trust boundary, product spec, and both design specs updated. Also in this batch: findings and report prose rewritten for the buyer with a prose test; Deal Room as what you uploaded / what we understood / what is missing; audit history in sentences with the viewer's zone named; new-deal form that refuses blank required numbers; report page with a 76-character column and chips that open the source; mobile nav labels and chat trigger clear of the bottom bar. Deferred with reasons in the response doc: external penetration test, five-user study, CVE scan, Docker topology run, unfamiliar-document validation, live-model injection measurement, the VoiceOver pass, chip size, a shortcuts preference |

## Verification

The lead runs the checks once at the end of the batch (parallel agents share `.next`, so `next build` and Playwright run only then) and fills this table.

| Check | Result |
|---|---|
| `pytest` (apps/api) | 172 passed (audit regressions, prose, chat providers, engine, ingest, API) |
| `bearcase eval` (mock provider) | PASS, 12/12 checks; extraction recall 19/19; status accuracy 19/19; 58/58 citations resolve; report v1 valid (36/36 material statements cited); Ask the Deal grounding ok |
| `ruff check` / `ruff format --check` / `mypy src` | clean (76 files) |
| `vitest` (apps/web) | 62 passed, run twice |
| `tsc --noEmit` / `eslint` | clean |
| `next build` | success |
| Playwright smoke (chromium + mobile) | 6 passed |
| Browser console on landing and app pages | no errors (only the Three.js Clock deprecation warning); scene-check ok incl. pause/resume |
| Screenshots | `docs/screenshots/01-13` recaptured from the running stack after phase 7 |

Live model: Google Gemini (gemini-3.8-flash, free tier) was exercised end to end on 2026-09-06 with the owner's key in `.env`: the chat resolved the backend, ran four tools, and returned a grounded, cited answer; a 503 "high demand" from the provider is mapped to a plain retry message. The Anthropic provider and the other OpenAI-compatible providers are covered by fake-client tests only. Docker Compose was written but not run (no Docker on this machine).

## Decisions that differ from the original package (deliberate)

1. **Zero-infrastructure default.** SQLite + local storage + in-process job runner so a clean checkout runs with `make seed && make dev`. PostgreSQL, S3/MinIO, and a polling worker are config switches (Docker Compose shows the full shape). Reason: the dev machine had no Docker; a portfolio demo must actually run.
2. **No pgvector.** The corpus is small and verification needs exact lexical/numeric overlap; a BM25 retriever sits behind a `Retriever` protocol.
3. **Numeric claims are settled by code, not the model**, in both providers. The model only judges narrative claims and drafts prose.
4. **Add-back review is rule-based against statement lines** (recurrence, prior-year excess, missing line) with human override that recomputes verified EBITDA. The rules do not establish a market salary or match a settlement; the trust boundary says so.
5. **The mock provider is a real rule-based extractor** over document text, not canned output; the same fixtures exercise the real parsing path.
6. **Chat `auto` mode connects the first key it finds.** Astra's copy required a provider to be named before any live call. `auto` stayed because the free-provider path depends on it; it is documented, `mock` pins the chat offline, and the panel always names the provider that answered.
7. **Astra's repairs were ported, not copied.** Its copy predates the multi-provider chat; each idea was re-implemented against the current tree, and its citation rule was narrowed to deal-scope replies so general answers are not flagged.

## File ownership

Phase 7 partition: `api/routes/demo.py` + `auth.py` (isolation), `ingest/validation.py` + `api/routes/documents.py` + `config.py` (limits), `chat/` + `components/domain/deal-chat.tsx` (chat wording and panel), `app/app/deals/[dealId]/page.tsx` (overview), `components/landing/` + `components/scene/` (hero), `ingest/statement_mapper.py` (mapping), documentation (`README.md`, `SECURITY.md`, `HANDOFF.md`, `docs/`). Suggested partition for future parallel work: `engine/` + `fixtures/` (finance), `ingest/` + `ai/` + `pipeline/` (platform), `apps/web/src/components/scene` (3D), everything else (product).

## Resume steps

1. `git status`; read this file, `CLAUDE.md`, and `docs/astra-review-response.md` (the deferred rows are the queue).
2. `make setup && make seed && make test && make eval`.
3. `make dev`, open `/demo` in two browsers and confirm each gets its own deal; walk the overview start section, the five sections (claims: "Confirm assessment" and "Ask about this claim"; financials: "What changed and why"; scenarios: the sticky result strip), the chat quick prompts, and the hero's three chapters with the pause control.
4. Next candidates, in order: connect a free provider (`GEMINI_API_KEY` or `GROQ_API_KEY` in `.env`) and record live chat grounding and injection numbers; document deletion through the API and retention for non-demo uploads; a shared rate limiter for multi-process deployments; reviewer comments UI (model exists); document version comparison; Anthropic-mode extraction run with recorded eval numbers; Lighthouse pass on the landing page.
