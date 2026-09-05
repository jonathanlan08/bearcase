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
- For Anthropic mode set `BEARCASE_AI_PROVIDER=anthropic` and provide `ANTHROPIC_API_KEY`.
- Add TLS, rate limiting, and monitoring at the edge; see `SECURITY.md` for known gaps.

## Read-only demo
Seed once, then deploy with the demo route enabled. Each visitor to `/demo` shares the demo analyst user; to isolate visitors, create per-session users in `routes/demo.py`.
