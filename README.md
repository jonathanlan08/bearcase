# BearCase AI

**Stress-test every claim before capital moves.**

BearCase AI is an open-source acquisition-diligence prototype. It extracts claims from deal documents, connects them to page- and cell-level evidence, verifies financial metrics with deterministic code, models downside scenarios, and assembles an investment-committee red-team report whose every material statement is cited.

[Live demo](#quick-start) · [Methodology](docs/formulas/README.md) · [Architecture](docs/architecture.md) · [Design](docs/design/README.md)

> The included Northstar HVAC deal is entirely fictional. BearCase is an educational prototype and does not provide financial, legal, tax, or investment advice.

![Landing page: the Evidence Core hero](docs/screenshots/01-landing-hero.png)

## Why BearCase

An acquisition thesis is spread across a CIM, financial statements, a customer export, contracts, debt terms, and a buyer model. First-pass review means repeatedly checking whether stated claims agree with the underlying evidence. BearCase turns that into a structured loop:

1. Open the fictional demonstration deal, or create a deal and upload documents.
2. Extract material claims with exact provenance.
3. Compare each claim with supporting and contradicting evidence.
4. Recalculate financial metrics with deterministic Python.
5. Stress-test the deal in base, downside, and severe scenarios.
6. Record human decisions and generate a citation-validated report.

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
- **Ask the Deal**: citation-first Q&A ("Why was adjusted EBITDA reduced?") answered only from persisted rows; every factual sentence cites evidence or a calculation, uncited sentences are removed, and each answer is stored with provider, prompt version, and an audit event
- Evaluation harness scoring extraction recall, status accuracy, contradiction precision, citation resolution, injection resistance, determinism, report validation, and Q&A grounding

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

Base-case DSCR is 1.34x against a 1.25x covenant; the downside case falls to 1.00x. Ground truth for every number lives in `fixtures/northstar-hvac/northstar-ground-truth.json` and is regenerated from a single Python source of truth.

## Quick start

Requirements: Python 3.12+ via [uv](https://docs.astral.sh/uv/), Node 20+. No Docker, database server, or API key is needed for the default setup.

```bash
git clone <this repo> bearcase && cd bearcase
make setup            # uv sync + npm install + copies .env.example to .env
make seed             # seeds the fictional Northstar deal into ./data/bearcase.db (~1s)
make dev              # API on :8000, web on :3000
```

Open http://localhost:3000 and choose **Explore the demo**. The API docs are at http://localhost:8000/api/docs.

### Mock mode and Anthropic mode

The default provider is `mock`: a deterministic rule-based extractor and comparator over the real document text. It drives the demo, tests, and evaluations offline. To use Claude:

```bash
BEARCASE_AI_PROVIDER=anthropic BEARCASE_AI_MODEL=claude-opus-5 ANTHROPIC_API_KEY=sk-ant-... make api
```

Output is validated against versioned Pydantic schemas before persistence; prompt, schema, model, and run id are stored with every extraction. Numeric verification stays in code in both modes.

### Docker Compose (PostgreSQL + MinIO + worker)

```bash
make docker-up
```

`infra/docker-compose.yml` runs the production shape: PostgreSQL, MinIO for S3-compatible storage, the API with `BEARCASE_JOB_RUNNER=poll`, a separate worker, and the web app.

## Testing and evaluation

```bash
make test        # pytest (unit + API integration) and vitest
make eval        # AI evaluation suite against Northstar ground truth
make e2e         # Playwright smoke tests (starts API and web)
make lint typecheck
```

The evaluation report lists twelve checks with pass/fail and detail. Both the tests and the evaluations run in CI (`.github/workflows/ci.yml`), along with a check that the committed ground truth matches the fixture generator.

## Screenshots

| Claim Audit: split view with rule-level explanation | Clickable cell citation opens the source |
|---|---|
| ![Claim Audit](docs/screenshots/04-claim-audit.png) | ![Citation viewer](docs/screenshots/09-citation-viewer.png) |

| Financial Verification: statement cells and add-back waterfall | Scenario Lab: five-year projection and DSCR |
|---|---|
| ![Financial Verification](docs/screenshots/05-financial-verification.png) | ![Scenario Lab](docs/screenshots/06-scenario-lab.png) |

| Red-Team Report with citations | Ask the Deal: citation-first Q&A |
|---|---|
| ![Report](docs/screenshots/07-report.png) | ![Ask the Deal](docs/screenshots/12-ask-the-deal.png) |

More: [Deal Room](docs/screenshots/03-deal-room.png), [overview](docs/screenshots/02-overview.png), [audit history](docs/screenshots/08-audit-history.png), [mobile landing](docs/screenshots/10-mobile-landing.png), [mobile claims](docs/screenshots/11-mobile-claims.png). Screenshots are captured with `npx tsx scripts/screenshots.ts` in `apps/web` against a running stack; the hero shows the reduced-motion static composition (the WebGL scene animates in the browser).

## Architecture

```
apps/web   Next.js 16 App Router, TypeScript strict, Tailwind v4, TanStack Query, Zod, Motion, React Three Fiber
apps/api   FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, PyMuPDF, openpyxl, Anthropic SDK
fixtures/  Northstar HVAC files and ground truth (generated by `bearcase generate-fixtures`)
docs/      design system, architecture, data model, AI trust boundary, formulas, implementation plan
infra/     Docker Compose and Dockerfiles
```

See [docs/architecture.md](docs/architecture.md) for the request and job flow, [docs/data-model.md](docs/data-model.md) for the 21 tables and their invariants, and [docs/ai-trust-boundary.md](docs/ai-trust-boundary.md) for what the model may and may not do.

### AI and code responsibilities

AI classifies documents, extracts and compares claims, ranks evidence, and drafts questions and narrative. Application code validates files, enforces per-user deal isolation, maps statements, performs every calculation, runs scenarios, validates citations, and stores the audit trail. The model is never the authority for a number. Every persisted metric stores its formula and input snapshot.

## Security and document handling

- Uploads are validated by extension, magic bytes, declared type, size, page/row limits, and SHA-256 duplicate check. Display names are sanitized; storage keys are generated server-side.
- PDFs are parsed with PyMuPDF for text and block positions only. Workbooks are opened read-only and data-only; formulas, macros, and links are never evaluated. CSVs are parsed with a strict schema.
- Document text is passed to the model inside `<document>` tags with an explicit rule that it is data, never instructions. Instruction-like text is detected, stored inert, and reported as a finding.
- Sessions are opaque tokens stored hashed with an httpOnly cookie; passwords use Argon2. Every deal-owned query is scoped to the owner.

See [SECURITY.md](SECURITY.md).

## Limitations

This is a portfolio prototype with synthetic data. Extraction can be incomplete or wrong and is meant to be reviewed. Financial outputs depend on mapped and reviewed inputs; interest-only and balloon debt are not modeled; IRR is periodic, not date-aware. Contract review is not legal advice. A real deployment would need stronger identity, retention, encryption, monitoring, compliance, and vendor-risk controls.

## License

MIT. See [LICENSE](LICENSE).
