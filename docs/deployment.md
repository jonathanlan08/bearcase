# Deployment guide

Three ways to run BearCase, from a laptop to a public URL:

| Path | What runs where | When |
|---|---|---|
| Local | SQLite, local files, API and web on one machine (`make dev`) | development, the default |
| Docker Compose | PostgreSQL, MinIO, API, worker, web in containers (`make docker-up`) | a single host you control |
| Render + Vercel (recommended for a public URL) | API and PostgreSQL on Render from `infra/render.yaml`; the Next.js app on Vercel, proxying `/api` to Render | a portfolio deployment on free tiers, or a small paid one |

Whichever path: run `bearcase migrate`, then `bearcase doctor`, before the first start. The rest of this page is the Render + Vercel walk-through, the Compose path, the environment variable table, what the Gemini free tier means for a deployment, and what a paid product would still need.

## Before the first start: migrate, then doctor

With `BEARCASE_ENV=production` the API does not run migrations on start (development mode does), and it refuses to start at all when `BEARCASE_SECRET_KEY` is still the value in this repository. So the first start of any environment is:

```bash
cd apps/api
uv run bearcase migrate   # applies the Alembic migrations to BEARCASE_DATABASE_URL
uv run bearcase doctor    # readiness table; exit code 1 on any failure
```

`bearcase doctor` reads the same settings the API would and prints one row per check, without ever printing a key:

```
BearCase doctor (bearcase 0.1.0)
  [ok  ] env          production
  [ok  ] database     postgresql reachable, migrated to 60fed1b30deb
  [warn] storage      local /app/data/storage, writable; on an ephemeral filesystem uploads vanish at the next deploy
  [ok  ] secret key   set, 43 characters
  [ok  ] chat         Google Gemini · gemini-3.8-flash; free tier: every user of this deployment shares one project's quota
  [ok  ] extraction   Rule-based mock (rules-v1); no key needed
  [ok  ] rate limits  on, 60/min per user (per client address before sign-in); in-process, so one API instance is assumed; X-Forwarded-For trusted
  [ok  ] quotas       25 MB per upload, 50 documents per deal, 500 MB per user, demo data kept 14 days
  [ok  ] cors         https://your-project.vercel.app
  [ok  ] job runner   thread: in-process, one worker thread
0 failures, 1 warning. Ready.
```

A failure (`fail`) is something the API cannot work without: the database is unreachable or behind the newest migration, storage cannot be written, the settings are invalid, or extraction is set to Anthropic without a key. A warning is a choice you should have made on purpose: the default secret in development, SQLite or local storage in production, `auto` chat with no key, the limiter off, a localhost CORS origin in production. `bearcase doctor --json` prints the same rows as JSON with a `ready` flag. The check resolves the chat backend from settings alone and never calls a provider, so it costs nothing and works offline.

In production mode the API also logs each warning at start (`bearcase.config`), and the startup line names the environment, database, storage, job runner, extraction provider, chat backend, and limiter, so a wrong deployment is visible in the first lines of the log.

## Render (API + PostgreSQL) and Vercel (web)

The browser only ever talks to the Vercel origin. The Next.js app rewrites `/api/*` to `BEARCASE_API_URL` (`apps/web/next.config.ts`), so the session cookie is set on the Vercel origin and CORS never comes into play for normal use; `BEARCASE_CORS_ORIGINS` is set to the Vercel origin anyway so a direct browser call from the app's origin also works. No `vercel.json` is needed for the rewrite.

### 1. Get a Gemini key

Create a key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey) (free tier, no card). Read [Model providers on a deployment](#model-providers-on-a-deployment) first if the deployment will see anything confidential.

### 2. Deploy the API on Render

1. Push the repository to GitHub.
2. In the Render dashboard choose **New → Blueprint** and select the repository. Render looks for `render.yaml` at the repository root; point it at `infra/render.yaml` when the dashboard asks for the path, or copy the file to the root.
3. The Blueprint creates a PostgreSQL database (`bearcase-db`) and a Docker web service (`bearcase-api`) built from `infra/api.Dockerfile`. It generates `BEARCASE_SECRET_KEY`, wires `BEARCASE_DATABASE_URL` from the database, and asks you for `GEMINI_API_KEY` (marked `sync: false`, so the value lives only in Render). Paste the key and apply.
4. The service starts with `bearcase migrate && bearcase doctor && bearcase serve --host 0.0.0.0 --port 8000`: migrations first, then the readiness check, and the API only serves when the check has no failure. Its output is in the service's log.
5. Note the service URL (`https://bearcase-api.onrender.com` or similar) and open `/api/health` on it. Leave `BEARCASE_CORS_ORIGINS` for after step 3 below.

What the Blueprint sets: `BEARCASE_ENV=production`, `BEARCASE_CHAT_PROVIDER=gemini`, `BEARCASE_JOB_RUNNER=thread` (jobs run on a thread inside the API process; no worker service), `BEARCASE_AI_PROVIDER=mock` (extraction stays rule-based), `BEARCASE_TRUST_PROXY_HEADERS=true` (Render's proxy appends the client address to `X-Forwarded-For`; the limiter reads the last hop), and `PORT=8000`.

Free-tier facts to plan around (check Render's current terms; they change): the free web service spins down after 15 idle minutes and the next request waits about a minute; the free database expires 30 days after creation and holds 1 GB, so a deployment that should outlive a month needs the smallest paid database plan; the filesystem is replaced on every deploy, so with the default local storage a document uploaded before a deploy cannot be reprocessed afterwards (claims, evidence, metrics, and decisions are in PostgreSQL and survive; the demo re-seeds per visitor and is unaffected). The Blueprint has commented blocks for S3-compatible storage (`BEARCASE_STORAGE_BACKEND=s3`; the image already contains boto3) and for a persistent disk on paid instance types.

### 3. Deploy the web app on Vercel

1. In Vercel choose **Add New → Project**, import the same repository, and set **Root Directory** to `apps/web` (framework: Next.js, detected).
2. Override the **Install Command** with `npm ci --legacy-peer-deps` (the repository installs with that flag everywhere; there is no `.npmrc`).
3. Environment variables, all for Production and Preview:
   - `BEARCASE_API_URL=https://bearcase-api.onrender.com` (the Render URL, no trailing slash). The rewrite is compiled at build time, so set it before the first build and redeploy after changing it.
   - `NEXT_PUBLIC_SITE_URL=https://your-project.vercel.app`
   - `NEXT_PUBLIC_GITHUB_URL=https://github.com/you/bearcase`
4. Deploy, then open `/demo` on the Vercel URL.
5. Back in Render, set `BEARCASE_CORS_ORIGINS` to `["https://your-project.vercel.app"]` (a JSON list, no trailing slash) and `BEARCASE_APP_BASE_URL` to `https://your-project.vercel.app`, the origin that verification, password-reset, and invite emails link to; the service restarts.

Two things to confirm on your deployment rather than assume: that a chat reply streams (text appears while it is generated) through the Vercel proxy rather than arriving in one piece, and that the first demo start after Render has spun down succeeds once the API is awake (retry if it fails). Before sign-in, rate limits are by client address; through the Vercel proxy every visitor reaches Render from Vercel's addresses, so demo start, sign-in, and registration share one budget per proxy address (`BEARCASE_RATE_LIMIT_PER_MINUTE`, 60 by default). After sign-in, including demo visitors, limits are per user and unaffected.

### 4. Email: console or Resend

Registration, password reset, and deal invitations send an email through `bearcase/email/`. The default `BEARCASE_EMAIL_PROVIDER=console` writes the message to the API log (the link included) and keeps the last 50 in memory; that is enough for a demo, for development, and for tests, and it means a deployment with no email service still works: an operator can copy a verification link out of the Render log for a tester. For real users switch to Resend:

1. Create a [Resend](https://resend.com) account, add and verify a sending domain you control (Resend gives you the DNS records), and create an API key.
2. On the API service set `BEARCASE_EMAIL_PROVIDER=resend`, `BEARCASE_RESEND_API_KEY` (as a secret, `sync: false` in the Blueprint), and `BEARCASE_EMAIL_FROM` to a sender on that domain, for example `BearCase <no-reply@yourdomain.com>`; the default `no-reply@bearcase.invalid` is a reserved domain that Resend will refuse.
3. Confirm `BEARCASE_APP_BASE_URL` is the Vercel origin (step 3.5). Links are built from this setting, never from the request, so a wrong value produces emails that point at localhost.
4. Register a test account on the deployment and check that the verification email arrives and that `/verify?token=...` reports the account verified; then try "Forgot password" on `/forgot`.

`ResendEmailer` posts to `https://api.resend.com/emails` with httpx; a failed send is logged and reported to the caller as a plain error, and no key is ever printed. Without a verified address an account can still sign in and work on its own deals; it cannot share a deal until it verifies.

### 5. Stripe Checkout for the bounded pilot

The `/pilot` page sells the per-deal pilot from `docs/go-to-market.md` through Stripe Checkout; the API never handles card details. Until both keys are set the page says checkout is not enabled and `POST /api/billing/checkout` answers 503, so a deployment without Stripe is fine.

1. In the [Stripe dashboard](https://dashboard.stripe.com/apikeys), start in **test mode** and copy the secret key (`sk_test_...`) into `BEARCASE_STRIPE_SECRET_KEY` on the API service (a secret, `sync: false`).
2. Under **Developers → Webhooks** add an endpoint with the URL `https://bearcase-api.onrender.com/api/billing/webhook` (the Render URL, not the Vercel one: the webhook is a server-to-server call and does not go through the Next.js rewrite) and subscribe it to `checkout.session.completed`. Copy the endpoint's signing secret (`whsec_...`) into `BEARCASE_STRIPE_WEBHOOK_SECRET`.
3. The price is `BEARCASE_PILOT_PRICE_CENTS` (50000, so $500.00) in `BEARCASE_PILOT_CURRENCY` (`usd`); there is no Stripe Product or Price object to create, the session is built with inline price data from these settings. Checkout returns to `{BEARCASE_APP_BASE_URL}/pilot?status=success&session_id=...` or `.../pilot?status=cancelled`.
4. Test it with Stripe's test card `4242 4242 4242 4242`: `GET /api/billing/status` should list the purchase as `pending` after the redirect and `paid` once the webhook has been delivered (the dashboard shows each delivery and its response code). Then switch both keys to live mode.

Locally, Stripe's CLI (`stripe listen --forward-to localhost:8000/api/billing/webhook`) prints a temporary `whsec_...` to use as the webhook secret. Tests never reach Stripe: the SDK is wrapped in an adapter with a fake implementation.

### Updating

Push to `main`: Render rebuilds the image and runs migrate → doctor → serve; Vercel rebuilds the web app. A migration that fails, or a doctor failure, keeps the previous Render deploy serving.

## Docker Compose

`make docker-up` starts PostgreSQL, MinIO, the API (`BEARCASE_JOB_RUNNER=poll`), a worker, and the web app on one host; seed with `docker compose -f infra/docker-compose.yml exec api bearcase seed`. The file is a development example: development credentials, `BEARCASE_ENV=development` (so the API migrates on start), and published ports. It has not been run on the development machine (no Docker there). For a host you expose, set `BEARCASE_ENV=production` and a real `BEARCASE_SECRET_KEY`, start the API with `bearcase migrate && bearcase doctor && bearcase serve ...` as the Render Blueprint does, keep MinIO and PostgreSQL off the public interface, and put a reverse proxy with TLS and a body-size limit in front.

## Environment variables

Every setting is a `BEARCASE_*` variable read from the environment or the repo-root `.env` (`apps/api/src/bearcase/config.py`); `.env.example` lists them with comments. Provider keys also accept their native names.

| Variable | Default | Notes |
|---|---|---|
| `BEARCASE_ENV` | `development` | `production` refuses the default secret, does not migrate on start, marks the session cookie Secure, and logs the warnings above |
| `BEARCASE_SECRET_KEY` | a development string | Session token hashes. 32+ random characters: `python -c 'import secrets; print(secrets.token_urlsafe(48))'` |
| `BEARCASE_DATABASE_URL` | SQLite under `./data` | `postgresql+psycopg://user:pass@host/db`; `postgres://` and `postgresql://` are rewritten to that driver |
| `BEARCASE_STORAGE_BACKEND` | `local` | `s3` needs `BEARCASE_S3_BUCKET`, optionally `BEARCASE_S3_ENDPOINT_URL` and `BEARCASE_S3_REGION`, and AWS credentials in the environment (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) |
| `BEARCASE_STORAGE_LOCAL_DIR` | `./data/storage` | Directory for the local backend |
| `BEARCASE_JOB_RUNNER` | `thread` | `poll` leaves jobs for `bearcase worker`; `sync` runs inline (tests, seeding) |
| `BEARCASE_AI_PROVIDER` / `BEARCASE_AI_MODEL` | `mock` / `claude-opus-5` | Extraction and report drafting; `anthropic` needs `ANTHROPIC_API_KEY` |
| `BEARCASE_CHAT_PROVIDER` | `auto` | `mock`, `anthropic`, `openai`, `gemini`, `groq`, `openrouter`, `ollama`, `custom`; `auto` takes the first key found in that order (anthropic, openai, gemini, groq, openrouter, ollama) |
| `BEARCASE_CHAT_MODEL` | provider default | Overrides the model id |
| `BEARCASE_CHAT_MODEL_PICKER` | `false` | Show the model picker in the chat panel |
| `BEARCASE_CHAT_MAX_OUTPUT_TOKENS` | `2048` | Output cap per chat request |
| `BEARCASE_CHAT_REASONING_EFFORT` | `low` | `none`, `low`, `medium`, `high` for providers that accept it |
| `BEARCASE_CHAT_MODEL_FALLBACK` | `true` | On a 5xx or an overloaded message on the first request of a reply, answer with the next model in the provider's fallback chain (`chat/providers.py`); a 429 never switches |
| `BEARCASE_CHAT_BRIEF_TTL_SECONDS` | `300` | How long a cached deal brief is trusted before its version stamp is rechecked |
| `BEARCASE_CHAT_BASE_URL` / `BEARCASE_CHAT_API_KEY` | unset | `custom` provider, or a gateway for a named provider; https except loopback and private networks |
| `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OLLAMA_HOST` | unset | Provider credentials; `GOOGLE_API_KEY` aliases Gemini, `ANTHROPIC_AUTH_TOKEN` counts as an Anthropic credential |
| `BEARCASE_CORS_ORIGINS` | `["http://localhost:3000"]` | JSON list of browser origins, no trailing slash |
| `BEARCASE_RATE_LIMIT_ENABLED` / `BEARCASE_RATE_LIMIT_PER_MINUTE` | `true` / `60` | Token bucket per user (client address before sign-in) on upload, reprocess, process, chat, ask, report, demo start, sign-in, registration |
| `BEARCASE_TRUST_PROXY_HEADERS` | `false` | Read the client address from the last `X-Forwarded-For` hop; only behind a proxy that appends it |
| `BEARCASE_MAX_UPLOAD_BYTES`, `BEARCASE_MAX_PDF_PAGES`, `BEARCASE_MAX_SHEET_ROWS`, `BEARCASE_MAX_CSV_ROWS` | 25 MB, 300, 20,000, 50,000 | Upload limits, checked after receipt and before parsing; add a body limit at the ingress |
| `BEARCASE_MAX_DOCUMENTS_PER_DEAL` / `BEARCASE_MAX_STORAGE_BYTES_PER_USER` | `50` / 500 MB | Storage quotas |
| `BEARCASE_SESSION_TTL_HOURS` | `336` | 14 days |
| `BEARCASE_DEMO_RETENTION_DAYS` | `14` | Demo visitors, their deals, and their files are deleted this long after their newest session expired |
| `BEARCASE_APP_BASE_URL` | `http://localhost:3000` | The web app's public origin, no trailing slash; verification (`/verify`), reset (`/reset`), and invite (`/invite`) links and the Stripe return URLs (`/pilot`) are built from it |
| `BEARCASE_EMAIL_PROVIDER` | `console` | `console` logs each email and keeps the last 50 in memory; `resend` sends through Resend and needs the two settings below |
| `BEARCASE_EMAIL_FROM` | `BearCase <no-reply@bearcase.invalid>` | Sender address; with `resend` it must be on a domain verified in Resend |
| `BEARCASE_RESEND_API_KEY` | unset | Resend API key, required for `resend`; a secret |
| `BEARCASE_CHAT_MONTHLY_REQUEST_LIMIT` | `300` | Assistant answers per user per calendar month (UTC), counted across every deal the user asked in, demo visitors included; the chat answers 429 with the reset date beyond it |
| `BEARCASE_STRIPE_SECRET_KEY` | unset | Stripe secret key (`sk_test_...` or `sk_live_...`); with it unset billing reports `configured: false` and checkout answers 503 |
| `BEARCASE_STRIPE_WEBHOOK_SECRET` | unset | Signing secret of the webhook endpoint `{api}/api/billing/webhook` subscribed to `checkout.session.completed` |
| `BEARCASE_PILOT_PRICE_CENTS` / `BEARCASE_PILOT_CURRENCY` | `50000` / `usd` | The bounded pilot's price in the smallest currency unit, and its currency |
| `BEARCASE_FIXTURES_DIR` | `fixtures/northstar-hvac` | The Docker image sets `/app/fixtures/northstar-hvac` |
| Web: `BEARCASE_API_URL` | `http://127.0.0.1:8000` | Where the Next.js rewrite sends `/api/*`; read at build time |
| Web: `NEXT_PUBLIC_SITE_URL`, `NEXT_PUBLIC_GITHUB_URL` | localhost, a placeholder | Canonical URL and the `/github` redirect |

## Model providers on a deployment

Free-tier cap, measured on 2026-09-06 with a fresh AI Studio key: 20 requests per day per model for gemini-3.8-flash (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`), plus a per-minute limit; a few hours of testing exhausted the day. Every user of the deployment draws on that one allowance. The cached deal brief keeps most answers to a single request, and a model that is busy or capped hands over to the next Gemini model in `chat/providers.py`, each with its own daily allowance, so a demo stretches to several dozen answers a day; anything beyond that needs a Google Cloud billing account on the paid tier, which also stops inputs being used for training.

One key serves every visitor. There is no per-visitor billing or key: whoever deploys the app pays for, and is accountable for, every chat the deployment answers. Choose deliberately:

- **Gemini free tier (the Blueprint default).** Free with no card, but the rate limit is per Google project, so all users of the deployment draw on the same budget: two people chatting at once can push the third into a 429. On the free tier Google may use inputs to improve its products; the chat sends claim text and evidence snippets from the deal to the provider. So the free tier suits the fictional demo and your own experiments, not confidential deals. For those, enable billing on the Google project (the key and the variable stay the same) or use another paid provider.
- **What the free tier felt like before tuning**, measured with `gemini-3.8-flash` on 2026-09-06: a successful long answer took 25 to 40 seconds because it needed four sequential tool rounds, each a separate provider request; one request spent 39 seconds inside the SDK's retries on a 503 "high demand" before failing; the next was refused with a 429 free-tier rate limit.
- **What the chat does about it.** A reply uses as few provider requests as possible (a cached deal brief, `BEARCASE_CHAT_BRIEF_TTL_SECONDS`, replaces the first tool rounds), reasoning effort defaults to `low`, output is capped (`BEARCASE_CHAT_MAX_OUTPUT_TOKENS`), and when the first request of a reply fails with a 5xx or an overloaded message the next model in the provider's fallback chain answers instead of retrying the busy one (`BEARCASE_CHAT_MODEL_FALLBACK`; for Gemini the chain runs `gemini-3.8-flash`, `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash-lite`). A 429 is reported as a plain "busy, try again" message and never switches models, because the quota is the project's, not the model's. The model picker is off by default so everyone gets the same model; `BEARCASE_CHAT_MODEL_PICKER=true` turns it back on. The chat panel still names the provider and model that answered.
- **No model bill at all:** `BEARCASE_CHAT_PROVIDER=mock`. The rule-based composer answers deal questions from persisted rows with citations; it does not do general-assistant answers.
- **Paid providers** (Anthropic, OpenAI, or Gemini with billing) do not train on API inputs under their standard API terms as of this writing, and their limits are per account rather than a shared free pool; read the current terms of the one you pick.

The API never returns or logs a key, and `bearcase doctor` names the backend by label and model only.

## What a paid product would still need

None of this exists yet; `SECURITY.md` has the full list of gaps, these are the ones that decide whether you can charge for it:

- A shared rate limiter (Redis or the database) so more than one API instance can run; today each instance keeps its own buckets and the Blueprint pins one instance.
- Account deletion and owner transfer; verification, password reset, and sharing with up to five collaborators exist, but an account and its deals can only be removed by an operator.
- Backups and restore drills for PostgreSQL and object storage, and retention plus deletion for documents outside the demo (documents cannot be deleted through the API).
- Monitoring and alerting: uptime, error rate, provider latency and 429s, and shipping of the audit log; today there is a health endpoint and the process log.
- Ingress body-size limits, parser CPU and memory bounds, a CSRF token, a dependency CVE scan in CI, and an external penetration test.
- Cost control beyond the per-user monthly answer count (`BEARCASE_CHAT_MONTHLY_REQUEST_LIMIT`): a per-customer key or a spend cap in currency, so one tenant's chat cannot exhaust the operator's provider quota within the month.
- Invoicing, refunds, and subscriptions: Stripe Checkout takes the per-deal pilot fee and the webhook records it; nothing else about money is automated.
