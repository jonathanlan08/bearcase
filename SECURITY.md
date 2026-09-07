# Security and privacy notes

BearCase is a portfolio prototype. These notes describe what it does today, not a production posture. An independent review on 2026-09-06 reproduced several gaps; `docs/astra-review-response.md` lists each one and its status.

## Threat model in scope

- Malicious or malformed uploads (wrong type, oversize, macro workbooks, zip bombs, path-like names)
- Prompt injection through document content
- Cross-user access to deals and evidence, including between demo visitors, and an invited collaborator acting beyond their role
- Account takeover through the email flows (guessable or reusable verification, reset, and invite tokens; invites accepted by the wrong account)
- A chat budget spent by one user against the operator's model quota
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
| Authentication | Argon2 password hashing; opaque session tokens stored as HMAC-SHA256 hashes; httpOnly, SameSite=Lax cookie, Secure in production mode; bearer header supported. Registration sends a verification link; `GET /api/auth/me` reports `email_verified`, the app shell shows a banner with a resend action until the address is verified, and sharing a deal requires a verified address |
| Email tokens | Verification, password-reset, and invite links carry a random urlsafe token; the database stores only its SHA-256 (`auth_tokens.token_hash`), so a database read does not yield a usable link. Each token is single use (`used_at`) and expires: 24 hours for verification, 1 hour for reset. `POST /api/auth/request-reset` always answers 200 whether or not the address exists, and a completed reset revokes every session of that user. `POST /api/auth/verify`, `/resend-verification`, `/request-reset`, and `/reset` are rate-limited by client address like sign-in. The link base is `BEARCASE_APP_BASE_URL`, set by the operator, never taken from the request's Host header |
| Email delivery | `bearcase/email/` is a small adapter: `ConsoleEmailer` (the default) logs the message and keeps the last 50 in memory for tests; `ResendEmailer` posts to Resend over https with `BEARCASE_RESEND_API_KEY`. No test or development path calls a mail service, and the key is never returned or logged |
| Authorization | Every deal-owned resource is fetched through the deal, and `get_deal` admits the owner or an accepted member (`deal_members.user_id` set and `accepted_at` set); anyone else gets 404. Roles are checked in code per action: an `editor` may do everything except delete the deal, manage members, or export the review dataset; a `viewer` may read, chat, and export seller questions but not upload, delete documents, run analysis, record decisions, or run scenarios. Audit rows record a member's actions under the member's own user id |
| Sharing | Only the owner, with a verified address, invites (`POST /api/deals/{id}/members`, at most five members per deal); the invite email links to `/invite?token=...`, and `POST /api/invites/accept` requires a signed-in account whose email matches the invitation case-insensitively, so a forwarded link cannot be accepted by someone else. The owner, or the member themselves, can remove a membership |
| Chat budget | Assistant answers are counted per user per calendar month (UTC) across all deals they asked in, demo visitors included; at `BEARCASE_CHAT_MONTHLY_REQUEST_LIMIT` (300) the chat route answers 429 with the reset date, and `GET /api/deals/{id}/chat/config` reports `budget: {limit, used, resets_on}`. This is the first per-user cap on the operator's model quota; the per-minute token bucket still applies |
| Payments | Stripe Checkout only: the API never sees card details. `POST /api/billing/checkout` creates a Checkout Session for the pilot price from settings (never from the request) and stores a `pending` purchase; `POST /api/billing/webhook` verifies the Stripe signature with `BEARCASE_STRIPE_WEBHOOK_SECRET` before reading the event and marks the purchase `paid` on `checkout.session.completed`, idempotently. The Stripe SDK sits behind an adapter with a fake used in tests, so no test reaches Stripe; without keys the routes answer 503 and report `configured: false` |
| Demo isolation | Each visitor to `/demo` gets a private demo identity (`visitor-<id>@demo.bearcase.invalid`, a reserved domain) and their own seeded copy of the Northstar deal; a caller with a live session, visitor or signed-in account, keeps that identity; sessions issued for the old shared demo user no longer resolve, so an old cookie yields a fresh visitor; a regression test checks that one visitor cannot read another visitor's deal. A visitor's identity, deals, and files are deleted 14 days after their newest session expired (`BEARCASE_DEMO_RETENTION_DAYS`); cleanup runs when a demo starts, at most 20 users per call, and a cleanup failure never blocks the demo. Demo start is rate-limited by client address |
| Document deletion | `DELETE /api/deals/{id}/documents/{document_id}` is owner-scoped through `get_deal` and returns 204; it removes the document row, its versions and stored files, the evidence read from it, and the claims whose source is that document together with their evidence links and reviewer decisions; the audit history keeps `document.deleted` with the document name and counts; the response header `X-BearCase-Reanalyse: true` tells the UI that findings and metrics may be stale and to offer "Run analysis"; deletion frees the deal's document count and the user's storage allowance |
| Retention | Demo visitors: identity, deals, and files are deleted 14 days after the newest session expires (`BEARCASE_DEMO_RETENTION_DAYS`, see Demo isolation). Signed-in accounts: uploads are kept until the owner deletes them; there is no automatic retention period yet, and the public `/trust` page states this together with which provider receives document text (extraction, when live) and claim text plus evidence snippets (chat). Exports that leave the system, the seller-questions file and the review dataset (`review_dataset.exported`, owner only), carry claim text and evidence snippets and are the owner's to keep or delete |
| AI boundary | Document text is wrapped as untrusted data; instruction-like text detected and stored inert; provider output validated against versioned schemas; citations must resolve or the claim is dropped; status guardrails enforced in code; chat reaches the deal only through read-only tools over persisted rows; context handed from a page into the chat is plain user text |
| Provider keys | Read from the environment or `.env` only; each key is sent only to its own provider's endpoint or to a gateway named in `BEARCASE_CHAT_BASE_URL` (https except loopback and private networks); no endpoint returns a key; keys are redacted from provider error text before it is streamed, stored, or logged |
| Immutability | Original extraction is never overwritten; reviewer decisions are additive rows; scenario results store input snapshots and hashes; audit events for every state change |
| Secrets | No secrets in the repository; `.env.example` documents configuration |
| Production mode | `BEARCASE_ENV=production` refuses to start with the development `BEARCASE_SECRET_KEY`, does not migrate on start, marks the session cookie Secure, and logs a warning for a localhost CORS origin, SQLite, local storage, `auto` chat with no key, and a disabled limiter (`config.py`); `bearcase doctor` prints the readiness table (database reachable and migrated, storage writable, secret set, chat and extraction providers by label, limits, quotas, CORS, job runner) and exits 1 on a failure, never printing a key |

## Production checklist

Before a URL is shared with anyone, in this order; `docs/deployment.md` has the walk-through.

1. `BEARCASE_ENV=production` with a `BEARCASE_SECRET_KEY` of 32 or more random characters (`python -c 'import secrets; print(secrets.token_urlsafe(48))'`, or Render's `generateValue`). The API refuses the checked-in default.
2. PostgreSQL in `BEARCASE_DATABASE_URL`; `bearcase migrate` before the first start (production does not migrate on start), then `bearcase doctor` with exit code 0.
3. Object storage (`BEARCASE_STORAGE_BACKEND=s3`) or a persistent disk for any deployment that accepts real uploads; the demo works on an ephemeral disk, real documents do not survive a deploy on one.
4. Provider keys, `BEARCASE_RESEND_API_KEY`, `BEARCASE_STRIPE_SECRET_KEY`, and `BEARCASE_STRIPE_WEBHOOK_SECRET` only as platform secrets (Render `sync: false`, Vercel environment variables), never in an image or the repository; one key serves every visitor, so decide who pays and whether a free tier's training terms are acceptable. `BEARCASE_CHAT_PROVIDER=mock` for a deployment with no model calls.
5. `BEARCASE_CORS_ORIGINS` set to the web app's origin as a JSON list without a trailing slash, and `BEARCASE_APP_BASE_URL` set to the same origin so verification, reset, and invite links point at your app; TLS everywhere; `BEARCASE_TRUST_PROXY_HEADERS=true` only behind a proxy that appends to `X-Forwarded-For` (Render does).
6. Rate limits on (`BEARCASE_RATE_LIMIT_ENABLED=true`, the default) and one API instance, because the limiter is in process memory; a body-size limit and a connection limit at the ingress, since the application checks the upload cap only after receiving the file.
7. Read the startup log line once: it names the environment, database, storage, job runner, extraction provider, chat backend, and limiter, and lists the production warnings.
8. Decide backups, retention, and monitoring before storing anything that matters. Owners can delete documents and demo data expires, but backups, an automatic retention period for accounts, and monitoring do not exist in the application (see the gaps below).

## Known gaps (not implemented)

Resource limits

- No request or body limits at the ingress. Put a reverse proxy in front with a body-size limit at or below the upload cap and a connection limit; the application limits are a second line, not the first.
- The rate limiter lives in one process. With several API processes each enforces its own budget; a public deployment needs one shared limiter.
- Parser CPU and memory are not bounded, and job concurrency is not limited beyond the single in-process runner.
- No retry or cost caps on live model calls; the extraction provider retries twice by default. `GET /api/deals/{id}/usage` reports tokens and an estimated cost per deal, which is tracking, not a cap.

Data handling

- No automatic retention period for uploads outside demo sandboxes; the owner deletes documents one at a time, and there is no account or deal deletion yet.
- The review-dataset export needs the deal owner's permission to be kept for evaluation; that permission is recorded by hand, not as a field on the deal.
- No encryption at rest beyond what the database or object store provides.
- No virus scanning of uploads.
- Free model tiers (Gemini free tier, OpenRouter `:free` endpoints) may log or train on what is sent; the chat sends claim text and evidence snippets.

Accounts and sessions

- No CSRF token (SameSite cookie only) and no account lockout beyond the per-address rate limit.
- Email verification is required to share a deal but not to sign in or upload; an unverified account can still use its own deals.
- Two roles (editor, viewer) on a deal with at most five members; no organisation, no owner transfer, and the review-dataset permission is still recorded by hand.
- Stripe Checkout takes the payment; there is no refund, invoice, or subscription handling in the app, and a `pending` purchase whose session expired is not tidied up.

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
