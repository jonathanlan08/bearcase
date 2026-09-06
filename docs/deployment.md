# Deployment guide

## Local (default)
`make setup && make seed && make dev`. SQLite database and file storage under `./data/`.

## Docker Compose
`make docker-up` starts PostgreSQL, MinIO, the API (`BEARCASE_JOB_RUNNER=poll`), a worker, and the web app. Seed with `docker compose -f infra/docker-compose.yml exec api bearcase seed`.

## Production shape
- Set `BEARCASE_ENV=production`, a long `BEARCASE_SECRET_KEY`, `BEARCASE_DATABASE_URL` (PostgreSQL), `BEARCASE_STORAGE_BACKEND=s3` with bucket and credentials, `BEARCASE_CORS_ORIGINS`.
- Run `bearcase migrate` before starting the API (production does not auto-migrate).
- Run one or more `bearcase worker` processes.
- Put the web app behind the same origin as the API (the Next.js rewrite proxies `/api`), or set `BEARCASE_API_URL`.
- Extraction and reports: for Anthropic mode set `BEARCASE_AI_PROVIDER=anthropic` and provide `ANTHROPIC_API_KEY`.
- Chat (Ask the deal): `BEARCASE_CHAT_PROVIDER=auto` (default) uses the first key present among `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, then `OLLAMA_HOST`, else the rule-based composer. Pin one by setting the provider name explicitly; `BEARCASE_CHAT_MODEL` overrides the model. Supply keys as environment variables or platform secrets, never baked into an image; the API never returns or logs them. A provider that cannot start (missing key, missing package, bad base URL) falls back to the composer and reports the reason in `GET /api/deals/{id}/chat/config`. `GOOGLE_API_KEY` is an alias for the Gemini key and `ANTHROPIC_AUTH_TOKEN` counts as an Anthropic credential. `BEARCASE_CHAT_BASE_URL` beside a named provider's key sends that key to your gateway instead of the public endpoint; the `custom` provider only ever uses `BEARCASE_CHAT_API_KEY`.
- Custom OpenAI-compatible servers (`BEARCASE_CHAT_PROVIDER=custom` with `BEARCASE_CHAT_BASE_URL` and `BEARCASE_CHAT_API_KEY`) and `OLLAMA_HOST` must use `https://`. Plain `http://` is accepted only for loopback and private-network hosts (for example `127.0.0.1`, `localhost`, or a `10.x`/`192.168.x` address), so a bearer key never crosses the public internet in clear text.
- Add TLS, rate limiting, and monitoring at the edge; see `SECURITY.md` for known gaps.

## Read-only demo
Seed once, then deploy with the demo route enabled. Each visitor to `/demo` shares the demo analyst user; to isolate visitors, create per-session users in `routes/demo.py`.
