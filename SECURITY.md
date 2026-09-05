# Security and privacy notes

BearCase is a portfolio prototype. These notes describe what it does today, not a production posture.

## Threat model in scope

- Malicious or malformed uploads (wrong type, oversize, macro workbooks, path-like names)
- Prompt injection through document content
- Cross-user access to deals and evidence
- Invalid or fabricated AI output reaching the database

## Controls

| Area | Control |
|---|---|
| Upload validation | Extension allowlist (pdf, xlsx, csv); magic-byte detection; extension/content mismatch rejected; declared MIME checked; 25 MB cap; page, sheet-row, and CSV-row limits; SHA-256 duplicate rejection per deal |
| Parser safety | PyMuPDF text/blocks only; openpyxl `read_only=True, data_only=True, keep_links=False`; VBA workbooks rejected; strict CSV schema; no content is ever executed |
| Storage | Server-generated object keys `deals/{deal}/documents/{doc}/v{n}/{sha}.{ext}`; local adapter refuses keys that escape the root; S3 adapter optional |
| Authentication | Argon2 password hashing; opaque session tokens stored as HMAC-SHA256 hashes; httpOnly, SameSite=Lax cookie; bearer header supported |
| Authorization | Every deal-owned resource is fetched through the deal and the deal through `owner_id`; cross-user access returns 404 |
| AI boundary | Document text is wrapped as untrusted data; instruction-like text detected and stored inert; provider output validated against versioned schemas; citations must resolve or the claim is dropped; status guardrails enforced in code |
| Immutability | Original extraction is never overwritten; reviewer decisions are additive rows; scenario results store input snapshots and hashes; audit events for every state change |
| Secrets | No secrets in the repository; `.env.example` documents configuration; API keys are read from environment or the Anthropic SDK's credential chain |

## Known gaps (not implemented)

- No rate limiting, CSRF token (SameSite cookie only), account lockout, or email verification
- No encryption at rest beyond what the database or object store provides
- No data-retention policy or deletion workflow for uploaded documents
- No virus scanning of uploads
- The in-process job runner is single-worker; multi-process deployments should use `BEARCASE_JOB_RUNNER=poll` with `bearcase worker`

## Reporting

Open an issue in the repository. Do not include real deal documents in reports.
