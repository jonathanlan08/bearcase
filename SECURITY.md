# Security and privacy notes

BearCase is a portfolio prototype. These notes describe what it does today, not a production posture. An independent review on 2026-09-06 reproduced several gaps; `docs/astra-review-response.md` lists each one and its status.

## Threat model in scope

- Malicious or malformed uploads (wrong type, oversize, macro workbooks, zip bombs, path-like names)
- Prompt injection through document content
- Cross-user access to deals and evidence, including between demo visitors
- Invalid or fabricated AI output reaching the database
- Resource and cost abuse of a public demo (large uploads, repeated processing, chat against a paid model)

## Controls

| Area | Control |
|---|---|
| Upload validation | Extension allowlist (pdf, xlsx, csv); magic-byte detection; extension/content mismatch rejected; declared MIME checked; 25 MB cap (`BEARCASE_MAX_UPLOAD_BYTES`) checked after the framework has received the file (spooled to disk above 1 MB) and before it is hashed or parsed; the request body itself is not bounded here, so put a body-size limit at the ingress; page cap (300), sheet-row cap (20,000), and CSV-row cap (50,000); XLSX archive budget on entry count and expanded size before the workbook is opened; SHA-256 duplicate rejection per deal |
| Storage quotas | 50 documents per deal (`BEARCASE_MAX_DOCUMENTS_PER_DEAL`) and 500 MB per user across all deals and versions (`BEARCASE_MAX_STORAGE_BYTES_PER_USER`), enforced by the upload route; a request refused for size or storage returns 413 and a full deal 400, each with a plain message naming the limit |
| Rate limits | Token bucket per signed-in user, or per client address before sign-in: 60 requests per minute (`BEARCASE_RATE_LIMIT_PER_MINUTE`) on the routes that parse, analyse, seed, or call a model (`POST /api/demo/session` and `/reset`, document upload and reprocess, `process`, `chat`, `ask`, report generation) plus sign-in and registration by client address; a spent budget returns 429 with `Retry-After`; off under `BEARCASE_ENV=test` unless set; `X-Forwarded-For` is honoured only with `BEARCASE_TRUST_PROXY_HEADERS=true` behind a proxy that overwrites it |
| Parser safety | PyMuPDF text/blocks only; openpyxl `read_only=True, data_only=True, keep_links=False`; VBA workbooks rejected; strict CSV schema; no content is ever executed |
| Storage | Server-generated object keys `deals/{deal}/documents/{doc}/v{n}/{sha}.{ext}`; local adapter refuses keys that escape the root; S3 adapter optional |
| Authentication | Argon2 password hashing; opaque session tokens stored as HMAC-SHA256 hashes; httpOnly, SameSite=Lax cookie, Secure in production mode; bearer header supported |
| Authorization | Every deal-owned resource is fetched through the deal and the deal through `owner_id`; cross-user access returns 404 |
| Demo isolation | Each visitor to `/demo` gets a private demo identity (`visitor-<id>@demo.bearcase.invalid`, a reserved domain) and their own seeded copy of the Northstar deal; a caller with a live session, visitor or signed-in account, keeps that identity; sessions issued for the old shared demo user no longer resolve, so an old cookie yields a fresh visitor; a regression test checks that one visitor cannot read another visitor's deal. A visitor's identity, deals, and files are deleted 14 days after their newest session expired (`BEARCASE_DEMO_RETENTION_DAYS`); cleanup runs when a demo starts, at most 20 users per call, and a cleanup failure never blocks the demo. Demo start is rate-limited by client address |
| AI boundary | Document text is wrapped as untrusted data; instruction-like text detected and stored inert; provider output validated against versioned schemas; citations must resolve or the claim is dropped; status guardrails enforced in code; chat reaches the deal only through read-only tools over persisted rows; context handed from a page into the chat is plain user text |
| Provider keys | Read from the environment or `.env` only; each key is sent only to its own provider's endpoint or to a gateway named in `BEARCASE_CHAT_BASE_URL` (https except loopback and private networks); no endpoint returns a key; keys are redacted from provider error text before it is streamed, stored, or logged |
| Immutability | Original extraction is never overwritten; reviewer decisions are additive rows; scenario results store input snapshots and hashes; audit events for every state change |
| Secrets | No secrets in the repository; `.env.example` documents configuration |

## Known gaps (not implemented)

Resource limits

- No request or body limits at the ingress. Put a reverse proxy in front with a body-size limit at or below the upload cap and a connection limit; the application limits are a second line, not the first.
- The rate limiter lives in one process. With several API processes each enforces its own budget; a public deployment needs one shared limiter.
- Parser CPU and memory are not bounded, and job concurrency is not limited beyond the single in-process runner.
- No retry or cost caps on live model calls; the extraction provider retries twice by default.
- Documents cannot be deleted through the API, so a full deal or a full storage allowance stays full until an operator intervenes.

Data handling

- No retention policy or deletion workflow for uploads outside demo sandboxes.
- No encryption at rest beyond what the database or object store provides.
- No virus scanning of uploads.
- Free model tiers (Gemini free tier, OpenRouter `:free` endpoints) may log or train on what is sent; the chat sends claim text and evidence snippets.

Accounts and sessions

- No CSRF token (SameSite cookie only), no account lockout, no email verification, no account recovery, no roles.
- The API does not refuse to start in production mode with the default `BEARCASE_SECRET_KEY`.

Operations

- No monitoring, alerting, or shipping of the audit log.
- The in-process job runner is single-worker; multi-process deployments should use `BEARCASE_JOB_RUNNER=poll` with `bearcase worker`.
- `infra/docker-compose.yml` is a development example: development credentials, development environment mode, published ports. It has not been run on the development machine.

Not done

- No dependency CVE scan is wired into CI.
- No external penetration test, load test, or infrastructure deployment has been performed.
- Live-model prompt-injection resistance has not been measured; the injection fixtures run through the mock provider only.

## Reporting

Open an issue in the repository. Do not include real deal documents in reports.
