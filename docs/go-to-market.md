# Go-to-market: the first customer

Working document, started 2026-09-06. Nothing in it has been tested with a customer yet. Every number is a target to test, not a result; replace it with the measured value when one exists.

## The promise

BearCase checks a seller's documents for financial inconsistencies and shows you what to investigate before buying the business.

That is the sentence for the landing page, the README, and the first minute of a call. Everything else in the product exists to deliver it: upload the seller's documents, see the important discrepancies, open the evidence behind each one, and export the questions to put to the seller.

What the sentence does not promise: a valuation, a recommendation to buy or not, legal or tax advice, or proof that a cited sentence is true (see "Risks and trust commitments").

## Whose problem it solves

First segment: a person buying their first small business, small enough that they read the documents themselves, who works with an accountant or an adviser (a buy-side broker, a lender's analyst, a fractional CFO). They have received a sales memo (CIM), two or three years of statements, maybe a customer list and a few contracts, and they have days, not weeks, to decide whether to spend money on a quality-of-earnings review. The seller's numbers are presented as facts. Checking them by hand means reading the CIM next to the statements with a spreadsheet open, and a first-time buyer does not know what to check or what "adjusted EBITDA" can hide.

Second segment: small acquisition teams (search funds, independent sponsors, a two- to five-person corporate development group) who look at many deals a year and want the first pass on each data room done the same way every time.

How to tell them apart in the first five minutes:

| Question | First-time buyer with an adviser | Small acquisition team |
|---|---|---|
| How many deals have you looked at in the last twelve months? | One or two; this may be the first | Five or more |
| Who reads the CIM first? | The buyer, then the accountant | An associate or analyst |
| What do they use today? | Email, a PDF reader, a spreadsheet the accountant built | A data room, a model template, sometimes a QoE firm |
| Who pays? | The buyer personally, sometimes through the adviser's fee | The firm |
| What do they want from BearCase? | To know what to ask before paying for a QoE | A consistent first pass and a hand-off list |
| What would make them stop? | Being wrong once about a number they relied on | Slower than their template, or nothing to export |

Start with the first segment. The pain is sharper (one deal, their own money), the workflow is short enough to support closely, and their adviser is the expert reviewer the reviewed-work set needs. The second segment has a longer sales cycle and asks for integrations first; it gets the next ten conversations if the first segment fails the kill criteria below.

Not now: lenders, sell-side brokers, QoE firms, corporate M&A. They may become channels later. They are not the customer.

## The one workflow

One workflow, end to end, with the chat helping people finish it rather than replacing it:

1. Upload documents (Deal Room): the sales memo, financial statements, customer list, contracts, loan terms. Run analysis.
2. See the important discrepancies (overview, then Claim Audit): the claims the documents disagree with, worst first, in plain words.
3. Inspect the evidence (citation viewer): the page or spreadsheet row the claim rests on, highlighted, and for numeric claims the calculation with its inputs.
4. Export questions for the seller (`/app/deals/[id]/questions`): one question per contradiction, unsupported claim, missing document, covenant warning, customer concentration, contract risk, or integrity finding, each with why it matters and the evidence it rests on, downloadable as Markdown or plain text. The report's "Management questions" section is built by the same function, so the page and the report never disagree.

The chat has two actions inside that workflow, both through `lib/chat-bus.ts`: "Explain this finding" prefills the chat with the finding's title; "Draft a question for the seller about this" sends at once and asks the model to cite the evidence ids. The chat answers only through read-only tools over persisted rows, and code checks every citation before the reply is stored.

The progress strip on the deal overview (`GET /api/deals/{id}/progress`) shows the four steps and which are done, so a first-time buyer always knows the next step. It is also how the usability test is logged.

## 30-day plan

Targets, not forecasts. A missed target is the finding.

| Week | Target | Evidence that counts |
|---|---|---|
| 1 | Ten conversations with people who bought, or tried to buy, a small business in the last two years, or with the accountants and advisers who helped them. Interview script below, run before showing the product. | Notes from ten calls; at least three who agree to a second session |
| 2 | Three closely supported pilots: the person uploads one real or anonymised document set while we watch on a screen share, without coaching, and we record the usability measures. | A document set they were permitted to share and did share; a second session they scheduled |
| 3 | Fix what blocked people in week 2. Re-run the usability task with the same three. | Completion and time, before and after |
| 4 | One paid pilot under the bounded offer below. | Money received, or a signed order, before delivery |

What counts as evidence: a shared, permitted document set; a second session the person scheduled themselves; a payment. What does not count: "this is cool", "I would definitely use this", a follow-up they did not schedule, an introduction they did not make. Log every conversation with one of four outcomes: nothing, shared a sample, scheduled a second session, paid.

Kill criteria for the segment (not for the product): fewer than three second sessions out of ten conversations, or no shared document set by the end of week 2. Either means the first-segment hypothesis is wrong and the second segment gets the next ten conversations.

## Interview script (before the demo)

Thirty minutes about their last deal, before they see BearCase. Take notes in their words; do not lead; do not describe the product until the end.

1. Tell me about the last business you looked at seriously. How did you hear about it, and what did the seller send you?
2. What did you check first? What did you check next? (Keep asking "and then?" until they stop.)
3. What took hours? What did you do by hand that felt like it should not be by hand?
4. What did you find out later that you wish you had known before the offer? What did you miss, and how did you find out?
5. Which tools did you use? A spreadsheet, a data room, a QoE firm, a template from a course, a friend. What did each cost?
6. Who else looked at the documents? What did the accountant or adviser do, and what did they charge?
7. Who paid for the diligence, and how much in total? Would you have paid more for an earlier answer?
8. If a list had shown you the discrepancies with the page each one came from, which of the things you missed would it have caught? Which would it not have caught?
9. What would make you distrust such a list?
10. Who else should I talk to? Ask for one name.

After the call, write down: the segment (from the table above), the hours they named, the miss they named, the tools and the money, and the outcome (nothing, sample, second session, paid).

## Usability test protocol

Purpose: measure whether someone can identify and explain a discrepancy without help. That is the product's core claim. If people cannot do it, nothing else matters.

Setup: their own document set if permitted, otherwise the Northstar demo (fictional; say so). Screen share. One observer who speaks only to give the task and to answer "is it over?". Use a fresh deal so the audit history and the progress strip start empty.

The task, read aloud once: "Find one thing in these documents that the seller's summary gets wrong, open the place in the documents it comes from, and tell me in your own words what it means for you as a buyer."

| Measure | How it is recorded |
|---|---|
| Completion | Did they open a claim or finding, open its source, and give an explanation? Three yes/no marks. |
| Time | Seconds from the end of the task being read to the end of their explanation. |
| Where they got stuck | The screen and the element where they paused longer than 20 seconds or asked a question. Note it; do not answer. |
| Explanation in their own words | Verbatim. Scored afterwards: names the two figures (what the seller says, what the documents show), names the source, says what it changes (price, risk, or a question to ask). Three yes/no marks. |
| Help requested | Count of questions asked. Each one is a defect to fix. |

Logging with the app: at the end, screenshot the progress strip on the overview (documents, findings, evidence, questions, each done or not). The audit history (`/app/deals/[id]/audit`) records `evidence.opened` when they open a source (one row per evidence per person per day), a reviewer decision when they confirm or correct a claim, `chat.reply` when they used the chat, and `seller_questions.exported` if they exported; keep it as the timing record. Tell participants about the logging after the task, not before.

Release threshold: four of five participants complete all three parts without help, in under ten minutes, and name the two figures and the source in their own words. Record every session in the usability table in `docs/evaluation.md`.

## Bounded pilot offer

What it is: one document set for one deal; BearCase's findings, plus a human check by us of every contradiction and every excluded add-back before delivery; the limitations in writing; delivered within five business days.

Deliverable: the seller-questions export (Markdown) and the red-team report (PDF). Each states what was checked, what was not, and that a citation shows where a statement came from, not that it is true.

Limitations stated up front: text-layer PDFs, XLSX, and CSV only; an income statement sheet must be named like one; no OCR, no monthly periods, no interest-only or balloon debt; add-back rules test recurrence and prior-year excess, not a market salary; a live model provider receives claim text and evidence snippets (named on `/trust`); nothing in the deliverable is investment, legal, or tax advice.

Price hypotheses, both to be tested in week 4, never both with the same person:

| Hypothesis | Starting price to test | Who it fits | What we learn |
|---|---|---|---|
| Per-deal fee | $500 per deal, set against one or two hours of the adviser's time | First-time buyer, one deal | Whether the buyer pays personally and how the price compares with the adviser's hourly rate |
| Monthly team plan | $300 per month for up to five deals | Small team | Whether the team wants it always on and how many deals it actually runs |

Ask for payment before delivery. A pilot that will not pay is a conversation and goes in the conversation log as one.

Taking the payment: the `/pilot` page of a deployment (linked from the landing page hero and footer) describes the offer, its limitations, and the price, and its "Start a pilot" button opens Stripe Checkout for the per-deal fee (`POST /api/billing/checkout`, optionally tied to one of the buyer's deals). The price and currency come from `BEARCASE_PILOT_PRICE_CENTS` and `BEARCASE_PILOT_CURRENCY` (defaults $500.00 USD, the per-deal hypothesis above); change the setting when the hypothesis changes rather than editing copy. The purchase is stored as `pending` when the session is created and marked `paid` by the signed Stripe webhook, and `GET /api/billing/status` lists the signed-in buyer's purchases, so "money received" in the plan above is a row with `status: paid`, not a screenshot. Until the Stripe keys are set the page explains that checkout is not enabled on this deployment and the route answers 503; the monthly team plan is not sold through the app yet. Setup is in `docs/deployment.md`; the Stripe test mode works end to end with test cards before any real charge.

## Cost tracking

Track four costs per deal from the first pilot: model cost, document processing, storage, and founder support time. The first three come from `GET /api/deals/{id}/usage`:

| Field | Meaning |
|---|---|
| `chat.messages`, `chat.input_tokens`, `chat.output_tokens`, `chat.tool_calls`, `chat.by_model` | What the chat consumed on this deal, with a count per model |
| `documents.count`, `documents.bytes`, `documents.pages`, `documents.rows` | What was uploaded and what was read from it |
| `storage_bytes` | Stored bytes across all document versions |
| `cost_estimate_usd` | Chat token cost from the price table in `chat/providers.py`; `null` when a model is not in the table |
| `pricing_note` | Which prices were used and their caveats |

Price table today, USD per million input and output tokens: Anthropic `claude-haiku-4-5` 1 and 5, `claude-sonnet-5` 2 and 10; OpenAI `gpt-5.6-luna` 0.20 and 1.20; Gemini free tier 0, with the note that paid tiers differ; Groq and OpenRouter free ids 0; any other model `null` with the note. Update the table when prices change. It is an estimate, not the invoice.

Model cost per answer is `cost_estimate_usd` divided by the assistant messages in `chat.messages`. Record it per pilot; it decides whether a per-deal price covers the model bill. Free tiers are priced at zero in the table and are not acceptable for a paid pilot (training terms, shared quota): price the paid tier.

Founder support time is not in the app. Log it by hand per deal in quarter hours, split into onboarding, answering questions, and human-checking the findings.

Unit-economics template, one row per pilot:

| Deal | Documents (count / MB / pages) | Chat messages | Tokens in / out | Model cost (USD) | Cost per answer | Support hours | Support cost at an hourly rate | Total cost | Price charged | Margin |
|---|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | | |

Processing and storage are close to zero at pilot scale (a small PostgreSQL, local or S3 storage). Write them down anyway, so the row is complete when they stop being zero.

## The reviewed-work flywheel

The advantage this product can build is a growing set of permissioned, expert-reviewed examples: claims where an accountant or adviser recorded a decision on the AI's status. Each pilot adds to the set; each release is measured against it.

1. During the pilot the reviewer confirms, corrects, or rejects each claim in the Claim Audit. Every decision is an additive row; the AI's original output stays as it was.
2. `GET /api/deals/{id}/review-dataset`, or `bearcase export-reviews --deal <id> --out file.jsonl` (all deals when `--deal` is omitted), exports one JSONL line per claim with at least one decision: the claim, the AI's status, rule, and rationale, the reviewer's action, status, value, and note, and the evidence the decision rested on (text capped at 200 characters). The export is owner-only and audited (`review_dataset.exported`).
3. `bearcase eval --reviews file.jsonl` prints agreement between `ai_status` and `reviewer_status`, overall and per claim type, and the count of corrections.
4. Before a release, run the regression suite on Northstar and the agreement check on the reviewed set. A drop in agreement blocks the release. `docs/evaluation.md` has the procedure.

Growing the set with permission: ask in writing, per deal, whether the claims and evidence snippets may be kept for evaluation, and keep the answer with the deal. Export only deals with a yes. The export carries claim text and evidence snippets, which can identify a company, so redact names before it leaves the team. Delete the export when the owner asks. Never keep a set from a deal where the answer was no, or was not asked.

The set is for measuring, not training. A larger set makes the agreement number mean more and shows which claim types the rules get wrong.

## Risks and trust commitments

Confident false output. The main risk of a generative model in this product is a fluent statement that is wrong; NIST AI 600-1, the generative AI profile of the AI Risk Management Framework, lists it under confabulation. BearCase's controls: the model never computes a number; every deal fact in the chat must come from a tool over persisted rows and carry a citation that code checks; a reply with an uncited figure is flagged. None of those controls checks that the cited source supports the sentence next to it. A resolving citation establishes provenance. It does not establish that the answer is correct. The product says "review the answer" and never "verified".

Commitments to a pilot customer, repeated on `/trust`:

- Documents are stored under server-generated keys, scoped to the owner, and can be deleted by the owner through the app. Deletion removes the file, its versions, its evidence, and the claims that came from it, and is recorded in the audit history. Findings and metrics may then be stale, and the app suggests running the analysis again.
- Demo uploads are removed 14 days after the visitor's newest session expires. Uploads to a signed-in account are kept until the owner deletes them; there is no automatic retention yet, and the trust page says so.
- Who sees what: extraction, when live, receives document text; the chat sends claim text and evidence snippets to the connected provider; the panel header names the provider and model. Free tiers may train on inputs, so a paid pilot runs on a paid tier.
- Four kinds of statement are told apart in the product: source facts (evidence with a locator), calculations (engine metrics with a formula and an input snapshot), assumptions (scenario inputs and add-back decisions), and AI interpretations (extracted claims, status rationale, narrative, chat). Each is labelled where it appears.
- The original AI output is never overwritten; reviewer decisions are additive.
- Nothing is investment, legal, or tax advice.

Other risks and what is done about them: a reviewer relies on a status without opening the source (the usability test measures whether they open it); a pilot shares a document they were not allowed to share (ask in writing); a free-tier quota runs out mid-pilot (paid tier for pilots); founder support time makes the unit economics negative (track it from the first pilot).

## One-page pitch outline

1. Problem: a first-time buyer receives the seller's summary and cannot easily tell which numbers the statements support. Discrepancies missed before closing cost money after it.
2. Who: a person buying their first small business, with an accountant or adviser. Second, small acquisition teams.
3. Promise: BearCase checks a seller's documents for financial inconsistencies and shows you what to investigate before buying the business.
4. How it works: upload, see the discrepancies, open the evidence, export the questions for the seller. Numbers are recomputed by code; every statement points at its source.
5. What is different: a claim ledger with provenance, not a chat over PDFs; immutable AI output with reviewer decisions; a reviewed-work set that measures each release.
6. Trust: what the provider sees, deletion and retention, provenance is not proof.
7. Evidence so far: the Northstar demo (fictional) and the regression suite; pilot results filled in as the 30-day plan runs.
8. Business: a per-deal fee or a team plan, both under test; unit economics from the `/usage` endpoint.
9. Ask: introductions to buyers and advisers; three pilot participants.
