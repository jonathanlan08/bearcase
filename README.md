# BearCase AI

**BearCase checks a seller's documents for financial inconsistencies and shows you what to investigate before buying the business.**

BearCase AI is an open-source prototype for reviewing a small-business acquisition. You add the seller's documents (the sales memo, financial statements, customer list, contracts, loan terms). BearCase pulls out the claims the seller makes, links each one to the page or spreadsheet cell it should rest on, recomputes the numbers in plain Python, tests what happens when things get worse, and writes a review in which every material statement points at its source.

**Who it is for.** A person buying their first small business, working with an accountant or an adviser, who has received a sales memo and a few years of statements and has days to decide what to ask before paying for a quality-of-earnings review. Second, small acquisition teams (search funds, independent sponsors, a two- to five-person corporate development group) that want the first pass on every data room done the same way. It is not for lenders, sell-side brokers, or corporate M&A, and it is not a chatbot over PDFs. The first-customer plan is in [docs/go-to-market.md](docs/go-to-market.md).

The workflow is one path: upload documents, see the important discrepancies, inspect the evidence, export questions for the seller. The chat helps you finish that path ("Explain this finding", "Draft a question for the seller about this") rather than replacing it.

[Demo](#quick-start) · [First session](#what-you-can-answer-in-a-first-session) · [Deploy](#deploy) · [Methodology](docs/formulas/README.md) · [Go-to-market](docs/go-to-market.md) · [Evaluation](docs/evaluation.md) · [Architecture](docs/architecture.md) · [Design](docs/design/README.md) · [Security](SECURITY.md) · [Review response](docs/astra-review-response.md) · How your documents are handled: the `/trust` page of any deployment (http://localhost:3000/trust locally)

> The included Northstar HVAC deal is entirely fictional. BearCase is an educational prototype and does not provide financial, legal, tax, or investment advice. Do not upload confidential documents to a public deployment yet; see [Limits](#limits).

![Landing page: the Evidence Core hero](docs/screenshots/01-landing-hero.png)

## What you can answer in a first session

A first session should let you answer four questions about a deal:

| Question | Where | What you see |
|---|---|---|
| What is the seller claiming? | Claim Audit | Each material claim with its status: supported, contradicted, unsupported, or review required, and the rule that decided it. |
| What does the evidence say? | The source, one click from any claim | The page paragraph or spreadsheet row the claim rests on, highlighted, so you can judge it yourself. |
| What could change my judgment? | Scenario Lab | Base, downside, and severe cases, with debt coverage against the lender's threshold. |
| What do I need from the seller? | Questions for the seller (`/app/deals/[id]/questions`) and the report | One question per contradiction, unsupported claim, missing document, covenant warning, concentration, contract risk, or integrity finding, each with why it matters and its evidence, exportable as Markdown or text. The report's "Management questions" section is built by the same function. |

The short path, on the demo or your own deal: upload documents, see the important discrepancies, inspect the evidence, export the questions for the seller. A progress strip on the deal overview shows those four steps and which are done; the start section names your next step and explains the two numbers most people ask about first (adjusted EBITDA and DSCR) in plain words.

## How it works

1. Open the fictional demonstration deal, or create a deal and upload documents.
2. Claims are extracted with exact provenance (page and paragraph, sheet and cell, or CSV row).
3. Each claim is compared with supporting and contradicting evidence.
4. Financial metrics are recalculated by deterministic Python, never by the model.
5. The deal is stress-tested in base, downside, and severe scenarios.
6. Your decisions are recorded and a citation-validated report is generated.

BearCase is not a document chatbot. Its primary object is a claim ledger with evidence links, calculations, review decisions, and an audit trail.

## Core capabilities

- PDF, XLSX, and CSV ingestion with content validation, hashing, duplicate rejection, and no execution of macros, formulas, or embedded objects
- Page/paragraph, sheet/row/cell, and CSV-row provenance on every evidence chunk
- Four claim statuses (supported, contradicted, unsupported, review required) with the deciding rule shown; absence of evidence is never contradiction
- Deterministic engine: growth, CAGR, margins, EBITDA reconciliation, add-back review, verified adjusted EBITDA, EV and leverage multiples, amortizing debt service, CFADS bridge, DSCR, cash-on-cash, periodic IRR, break-even
- Base, downside, and severe scenarios with immutable input snapshots, a five-year projection, and a DSCR sensitivity grid
- Immutable AI output with additive, audited reviewer decisions (accept, reject, correct, undo)
- Report validation: material statements must cite evidence or a calculation, or the report fails
- Anthropic provider behind an interface plus a deterministic rule-based mock that needs no API key
- Prompt-injection fixtures stored as inert document text and surfaced as findings
- **Ask the deal**: a streaming chat that works like a general assistant and also knows the deal. General questions (finance and M&A concepts, writing, code, anything else) are answered directly, in Markdown. Facts about the deal come only through eight read-only tools over persisted rows (claim ledger, verified metrics, add-back decisions, scenario results, findings, document search) and carry citation markers that code checks against the deal's evidence and metrics before the reply is stored; each one renders as a chip that opens the source. A resolving citation shows where a statement came from; it does not prove the statement is true, so the footer asks you to open the sources rather than claiming the answer is verified. Every reply is labelled by scope (deal evidence or general answer), a deal reply with an uncited figure is flagged, replies can be copied or regenerated, and conversations are stored per deal. Four quick prompts sit under the box (explain this finding, what should I ask the seller, what is missing, what changed after this scenario), and "Ask about this claim" on any claim or add-back hands its text, status, and numbers into the chat so you do not retype them. Works with Anthropic, OpenAI, Google Gemini, Groq, OpenRouter, a local Ollama, or any OpenAI-compatible server, with a model picker for the connected provider; without a key the same chat runs on the deterministic rule-based composer
- Evaluation harness scoring extraction recall, status accuracy, contradiction precision, citation resolution, injection resistance, determinism, report validation, and Q&A grounding against the Northstar ground truth

## The fictional demonstration

The Northstar HVAC Services deal intentionally contains discrepancies:

| The seller says | The evidence shows |
|---|---|
| 18% annual revenue growth (CIM p.3) | 11.6% CAGR FY2022–FY2024 (statements) |
| No customer above 10% (CIM p.5) | Apex Logistics Park is 22.0% (customer file) |
| $2.10M adjusted EBITDA (CIM p.3) | $1.81M after add-back review |
| 85% recurring revenue (CIM p.5) | 68.0% under maintenance agreements |
| Apex contract through 2027, auto-renewing (CIM p.6) | Initial term ends 2026 with 60-day termination for convenience |
| Temporary labor was one-time (CIM p.7) | Present in all three years |

Base-case DSCR is 1.34x against a 1.25x covenant; the downside case falls to 1.00x. Ground truth for every number lives in `fixtures/northstar-hvac/northstar-ground-truth.json` and is regenerated from a single Python source of truth. These are outputs of a fictional fixture, not an assessment of any real acquisition.

## Quick start

Requirements: Python 3.12+ via [uv](https://docs.astral.sh/uv/), Node 20+. No Docker, database server, or API key is needed for the default setup.

```bash
git clone <this repo> bearcase && cd bearcase
make setup            # uv sync + npm install + copies .env.example to .env
make seed             # seeds the fictional Northstar deal into ./data/bearcase.db (~1s)
make dev              # API on :8000, web on :3000
```

Open http://localhost:3000 and choose **Explore the demo**. The API docs are at http://localhost:8000/api/docs.

### The demo is yours alone

Each visitor to `/demo` gets their own demo user and their own copy of the Northstar deal. Anything you create, upload, or decide while in demo mode is visible only to your browser session; another visitor gets a fresh copy and cannot open yours. A signed-in account keeps its own identity when it opens the demo. Demo sandboxes are not backed up. A visitor's demo identity, deals, and files are deleted 14 days after their newest session expires (`BEARCASE_DEMO_RETENTION_DAYS`), cleaned up a few at a time when a new demo starts. See [SECURITY.md](SECURITY.md) for the limits that apply.

### Connecting a model

The default is `mock`: no key, no network. A deterministic rule-based extractor and comparator runs over the real document text and drives the demo, tests, and evaluations offline; the chat runs on a rule-based composer over the same rows. The composer only answers deal questions; the general-assistant behaviour described below needs a live model.

To put a live model behind the chat ("Ask the deal", ⌘/ inside a deal), add one key. With `BEARCASE_CHAT_PROVIDER=auto` (the default) the API uses the first key it finds, checking anthropic, openai, gemini, groq, openrouter, then ollama when `OLLAMA_HOST` is set. Set `BEARCASE_CHAT_PROVIDER=mock` to keep the chat offline whatever keys are present. The free options come first in this table:

| Provider | Env var | Free? | Default model | Get a key |
|---|---|---|---|---|
| Google Gemini | `GEMINI_API_KEY` | Yes, free tier without a card; per-project rate limits are shown in AI Studio | `gemini-3.8-flash` | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| Groq | `GROQ_API_KEY` | Yes, free plan without a card; rate-limited per organization | `openai/gpt-oss-120b` | [console.groq.com/keys](https://console.groq.com/keys) |
| OpenRouter | `OPENROUTER_API_KEY` | Yes, `:free` models cost nothing; a low daily request cap applies until you buy credits | `z-ai/glm-5.2:free` | [openrouter.ai/keys](https://openrouter.ai/keys) |
| Ollama (local) | `OLLAMA_HOST` | Yes, runs on your machine with no key; `qwen3:8b` is about 5 GB and suits 16 GB of RAM, use `qwen3:4b` on 8 GB | `qwen3:8b` | [ollama.com/download](https://ollama.com/download), then `ollama pull qwen3:8b` |
| OpenAI | `OPENAI_API_KEY` | No, prepaid credits | `gpt-5.6-luna` | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| Anthropic | `ANTHROPIC_API_KEY` | No, prepaid credits; new Console accounts get a small one-time test credit, and a claude.ai subscription does not include API access | `claude-haiku-4-5` | [platform.claude.com/settings/keys](https://platform.claude.com/settings/keys) |

Prices and rate limits change; check the provider's pricing page before relying on a free tier. Free tiers may log or train on what you send (Gemini's free tier and OpenRouter's free endpoints say so), and the chat sends claim text and evidence snippets from the deal to the provider, so keep real deal documents off them. On a deployment every visitor's chat runs on the operator's one key: on the Gemini free tier that means all users share one project's rate limit and its training terms, and on a paid plan one bill; `BEARCASE_CHAT_PROVIDER=mock` runs a deployment with no model bill at all.

Three steps:

1. `cp .env.example .env` if the file is missing (`make setup` creates it).
2. Add one line, for example `GEMINI_API_KEY=...` (for Ollama, `OLLAMA_HOST=http://127.0.0.1:11434`).
3. Restart the API with `make api` (or `make dev`).

The chat header shows the provider and model that answered. When a live provider is connected, the header also has a model picker with that provider's models, default first:

| Provider | Models in the picker |
|---|---|
| Anthropic | `claude-haiku-4-5`, `claude-sonnet-5`, `claude-opus-5` |
| OpenAI | `gpt-5.6-luna`, `gpt-5.6-terra`, `gpt-4.1-mini`, `gpt-4o-mini` |
| Google Gemini | `gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3.5-flash-lite`, `gemini-2.5-flash`, `gemini-2.5-flash-lite` |
| Groq | `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `qwen/qwen3.6-27b`, `qwen/qwen3.8-27b` |
| OpenRouter | `z-ai/glm-5.2:free`, `nvidia/nemotron-3-super-120b-a12b:free`, `minimax/minimax-m3:free`, `google/gemma-4-31b-it:free` |
| Ollama | `qwen3:8b`, `qwen3:4b`, `llama3.1:8b`, `llama3.2:3b`, `mistral:7b`, `gpt-oss:20b` |
| custom | the configured model only (`BEARCASE_CHAT_MODEL`) |
| mock | `rules-v1` |

If `BEARCASE_CHAT_MODEL` is set it appears first. The picked id is sent as `model` on `POST /api/deals/{id}/chat` and checked on the server: it must match `^[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}$` and, when a live provider is connected, be one of the ids in that provider's `models` list; anything else is a 400 (`Model is not offered for the connected provider.` for an id outside the list). The mock ignores the field. The id that answered is recorded on the stored messages. Lists change as providers retire models; a listed id the provider no longer knows produces a plain error in the chat rather than a crash. `GET /api/deals/{id}/chat/config` returns the provider, model, and the `models` list, plus a plain-language note when a configured provider could not start; in that case the chat falls back to the composer instead of failing.

- Extraction and reports still use `BEARCASE_AI_PROVIDER` (`mock` or `anthropic`) with `BEARCASE_AI_MODEL`. Chat and extraction are independent: the chat can run on Gemini while extraction stays on the mock, or the other way round. To use Claude for extraction:

  ```bash
  BEARCASE_AI_PROVIDER=anthropic BEARCASE_AI_MODEL=claude-opus-5 ANTHROPIC_API_KEY=sk-ant-... make api
  ```

- With a live model the chat behaves like a general assistant: it answers general questions (finance concepts, writing, code, anything else) directly and in Markdown, and it also knows the deal. Deal facts come only from the eight read-only tools (`apps/api/src/bearcase/chat/tools.py`) and the same code-side citation check applies to every provider: each `[E:…]`/`[M:…]` marker must match evidence or a metric that belongs to this deal, or it is dropped before the reply is stored. Markers inside fenced code blocks or backtick spans are shown literally and are neither checked nor counted. The model is told not to compute new deal numbers (what-ifs go to the Scenario Lab), not to recommend buying, rejecting, or pricing the deal, and to phrase general knowledge as general rather than as deal evidence. The note that the deal is fictional is added to the prompt only for the demo deal; your own deals are treated as real user data.
- Every reply is labelled by scope and checked for grounding. The check works per paragraph (blank-line separated): a paragraph that contains a figure (`$`, `%`, or a digit) must carry a citation marker, and a reply that touched the deal (a tool ran, or a figure appears) must carry at least one resolved marker overall. Heading lines and ordered-list numbers (`## 3 risks`, `1. Owner salary`) do not count as figures on their own, and code is skipped. `general` means nothing in the turn touched the deal: no tool ran, no marker resolved, and no uncited figure appeared; the footer then reads "General answer, not from the deal room". Any other reply is `deal`. A deal reply with an uncited figure is flagged in the footer with the count of cited paragraphs; a fully cited one says how many citations resolve ("All 4 citations resolve · review the answer") and asks you to review the answer. What the check proves: that every marker points at real evidence or a real metric in this deal. What it does not prove: that the cited source supports the sentence next to it. Open the chip and read the source. The scope and grounding flag are stored with the message and sent in the `citations` and `done` stream events; text streams before the check runs, and the footer appears when the check finishes.
- Replies render Markdown (headings, lists, bold, tables, fenced code) with citation chips inline, and each reply has copy and regenerate actions. If the connection drops while a reply is streaming (closing the tab, stopping the request), the text received so far is stored with the error "Stopped before the reply finished." and can be regenerated; a stored reply with no text and no error shows "No reply was recorded."
- A model without tool calling falls back automatically to a grounded single-shot mode: code pre-fetches the persisted rows the tools would have returned, the model drafts from those, and the same citation check and scope label apply.
- To pin a provider, set `BEARCASE_CHAT_PROVIDER` to one of `mock`, `anthropic`, `openai`, `gemini`, `groq`, `openrouter`, `ollama`, `custom`; `BEARCASE_CHAT_MODEL` overrides the default model. For any other OpenAI-compatible server use `custom` with `BEARCASE_CHAT_BASE_URL` and `BEARCASE_CHAT_API_KEY` (https, except for loopback or private-network hosts); `custom` never borrows another provider's key. Setting `BEARCASE_CHAT_BASE_URL` next to a named provider's key routes that provider through your own gateway instead of its public endpoint, under the same https rule.
- Keys are read from the environment or `.env` only; no endpoint returns them and they are not logged. `GOOGLE_API_KEY` is accepted as an alias for `GEMINI_API_KEY`, and `ANTHROPIC_AUTH_TOKEN` (read by the Anthropic SDK itself) counts as an Anthropic credential in auto mode.

No live model has been exercised end to end in this repository's development environment (no key was available); the tool loop, the fallback, error mapping, and key handling are covered by tests with fake clients. If you connect a key and something looks off, the `chat/config` note and the chat's error text are the first places to look.

Extraction output is validated against versioned Pydantic schemas before persistence; prompt, schema, model, and run id are stored with every extraction. Numeric verification stays in code in every mode.

### Docker Compose (PostgreSQL + MinIO + worker)

```bash
make docker-up
```

`infra/docker-compose.yml` runs the production shape: PostgreSQL, MinIO for S3-compatible storage, the API with `BEARCASE_JOB_RUNNER=poll`, a separate worker, and the web app. It is a development example with development credentials and published ports, not a hardened configuration, and it has not been run on the development machine (no Docker there).

## Deploy

The recommended public setup is Render for the API and PostgreSQL and Vercel for the web app: `infra/render.yaml` is a Render Blueprint (database, Docker API service, generated secret, the Gemini key entered in the dashboard), and the web app needs only `BEARCASE_API_URL` set to the Render URL because Next.js proxies `/api` to it.
Before the first start run `bearcase migrate`, then `bearcase doctor`: it prints a readiness table (database reachable and migrated, storage writable, secret set, which model answers by label, limits and quotas) and exits 1 on a failure; the Blueprint runs both before every start.
With `BEARCASE_ENV=production` the API refuses the development secret and logs a warning for localhost CORS origins, SQLite, local storage, `auto` chat with no key, or a disabled limiter.
One API instance is assumed: the rate limiter lives in process memory.
On the Gemini free tier all visitors share one project's rate limit and inputs may be used for training, so a deployment for confidential deals needs a paid plan or `BEARCASE_CHAT_PROVIDER=mock`. Measured on 2026-09-06: the free tier allowed 20 requests per day per model for gemini-3.8-flash (quota id GenerateRequestsPerDayPerProjectPerModel-FreeTier), which a few hours of testing used up. The cached deal brief keeps most answers to one request, and a model that is busy or has hit its per-model cap hands over to the next Gemini model, each with its own daily allowance, so a demo stretches further; a product with real users needs the paid tier.
Step by step, the Docker Compose path, the environment variable table, and what a paid product would still need are in [docs/deployment.md](docs/deployment.md).

## Testing and evaluation

```bash
make test        # pytest (unit + API integration) and vitest
make eval        # AI evaluation suite against Northstar ground truth
make e2e         # Playwright smoke tests (starts API and web)
make lint typecheck
```

The evaluation report lists each check with pass/fail and detail. Both the tests and the evaluations run in CI (`.github/workflows/ci.yml`), along with a check that the committed ground truth matches the fixture generator.

What the evaluation proves: that the pipeline still produces the expected result on the Northstar fixtures with the mock provider. What it does not prove: extraction accuracy on documents it has never seen, or prompt-injection resistance of a live model. Measuring those needs an independently labelled set of unfamiliar deals (messy workbooks, scanned PDFs, conflicting versions, missing documents) and a real key; neither exists in this repository yet.

The second instrument is the reviewed-work set: every reviewer decision on a claim sits next to the AI's original output, and `bearcase export-reviews --deal <id> --out file.jsonl` (or `GET /api/deals/{id}/review-dataset`, owner only, audited) exports one JSONL line per reviewed claim. `bearcase eval --reviews file.jsonl` prints the agreement between the AI's status and the reviewer's, overall and per claim type, plus the count of corrections. How both instruments gate a release, and the release record, are in [docs/evaluation.md](docs/evaluation.md).

## Screenshots

| Claim Audit: split view with rule-level explanation | Clickable cell citation opens the source |
|---|---|
| ![Claim Audit](docs/screenshots/04-claim-audit.png) | ![Citation viewer](docs/screenshots/09-citation-viewer.png) |

| Financial Verification: statement cells and add-back bridge | Scenario Lab: five-year projection and DSCR |
|---|---|
| ![Financial Verification](docs/screenshots/05-financial-verification.png) | ![Scenario Lab](docs/screenshots/06-scenario-lab.png) |

| Red-Team Report with citations | Ask the deal |
|---|---|
| ![Report](docs/screenshots/07-report.png) | ![Ask the deal](docs/screenshots/12-ask-the-deal.png) |

More: [Deal Room](docs/screenshots/03-deal-room.png), [overview](docs/screenshots/02-overview.png), [audit history](docs/screenshots/08-audit-history.png), [mobile landing](docs/screenshots/10-mobile-landing.png), [mobile claims](docs/screenshots/11-mobile-claims.png). Screenshots are captured with `npx tsx scripts/screenshots.ts` in `apps/web` against a running stack; the hero shows the reduced-motion static composition (the WebGL scene animates in the browser). Some screenshots predate the 2026-09-06 changes (overview start section, "What changed and why" on financials, the sticky scenario result strip, the wider chat panel with quick prompts, the three-chapter hero with captions and a pause control).

## Architecture

```
apps/web   Next.js 16 App Router, TypeScript strict, Tailwind v4, TanStack Query, Zod, Motion, React Three Fiber
apps/api   FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, PyMuPDF, openpyxl, Anthropic SDK, OpenAI-compatible client
fixtures/  Northstar HVAC files and ground truth (generated by `bearcase generate-fixtures`)
docs/      design system, architecture, data model, AI trust boundary, formulas, go-to-market, evaluation, implementation plan, review response
infra/     Docker Compose and Dockerfiles
```

See [docs/architecture.md](docs/architecture.md) for the request and job flow, [docs/data-model.md](docs/data-model.md) for the tables and their invariants, and [docs/ai-trust-boundary.md](docs/ai-trust-boundary.md) for what the model may and may not do.

### AI and code responsibilities

AI classifies documents, extracts and compares claims, ranks evidence, and drafts questions and narrative. Application code validates files, enforces per-user deal isolation, maps statements, performs every calculation, runs scenarios, checks citations, and stores the audit trail. The model is never the authority for a number. Every persisted metric stores its formula and input snapshot.

## Security and document handling

- Uploads are validated by extension, magic bytes, declared type, size (25 MB, checked before the file is hashed or parsed; put a body limit at the ingress for a public deployment), page and row limits, an archive budget for XLSX files, and a SHA-256 duplicate check. Display names are sanitized; storage keys are generated server-side.
- PDFs are parsed with PyMuPDF for text and block positions only. Workbooks are opened read-only and data-only; formulas, macros, and links are never evaluated. CSVs are parsed with a strict schema.
- Document text is passed to the model inside `<document>` tags with an explicit rule that it is data, never instructions. Instruction-like text is detected, stored inert, and reported as a finding.
- Sessions are opaque tokens stored hashed with an httpOnly cookie; passwords use Argon2. Every deal-owned query is scoped to the owner. Demo visitors are isolated from each other.
- The routes that parse, analyse, seed, or call a model (demo start, upload, reprocess, process, chat, ask, report generation, plus sign-in and registration by client address) have a per-user token-bucket rate limit (60 per minute by default; 429 with `Retry-After`), and storage is capped at 50 documents per deal and 500 MB per user. There are no ingress body limits yet, and the limiter is per process.
- The owner can delete a document (`DELETE /api/deals/{id}/documents/{document_id}`): the file, its versions, its evidence, and the claims that came from it are removed, the event is recorded, and the app suggests running the analysis again because findings and metrics may be stale. Demo uploads are removed 14 days after the visitor's newest session expires; uploads to a signed-in account are kept until the owner deletes them. The `/trust` page explains retention and which provider sees what.

See [SECURITY.md](SECURITY.md) for the full list of controls and known gaps.

## Limits

This is a portfolio prototype with synthetic data. Read these before relying on anything it produces.

- **Extraction can be incomplete or wrong.** Every claim is meant to be reviewed; the status rule and the source are shown so you can check them.
- **A citation proves provenance, not truth.** The code checks that a citation points at real evidence or a real metric in this deal and lets you open it. It does not check that the source supports the sentence next to it. In the chat this means a reply can cite a real but unrelated row and still pass the link check.
- **Add-back rules are narrow.** They test whether an expense recurs and whether it exceeds the prior year. They do not establish a market replacement salary for the owner or match a legal expense to a settlement; the reviewer's decision on each adjustment is the verification, and verified adjusted EBITDA changes with it.
- **Confidence scores are not calibrated.** The confidence on a claim is the extractor's confidence that the sentence is a material claim (or the rule score in mock mode), not a probability that the claim is true; the status carries the judgement.
- **Document handling is limited.** PDF, XLSX, and CSV only; text-layer PDFs only (no OCR); an income statement sheet must be named like one (`Income Statement`, `P&L`, `Profit and Loss`); no manual mapping, currency handling, monthly periods, or version comparison yet.
- **Financial modelling is limited.** Outputs depend on mapped and reviewed inputs; interest-only and balloon debt are not modelled; IRR is periodic, not date-aware; the sensitivity grid varies two inputs.
- **The evaluation is a regression check** on the Northstar fixtures with the mock provider, not an accuracy measurement on unfamiliar documents. No live model has been run end to end here.
- **Not ready for confidential deals.** Demo isolation with retention, rate limits, storage quotas, and owner deletion of documents exist; ingress body limits, a shared limiter across API processes, automatic retention for your own uploads, monitoring, encryption at rest, CSRF tokens, account recovery, a dependency CVE scan, and an external penetration test do not. Free model tiers may log what you send.
- **Contract review is not legal advice**, and nothing here is investment advice.

## License

MIT. See [LICENSE](LICENSE).
