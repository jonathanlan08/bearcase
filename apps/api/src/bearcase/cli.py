"""BearCase command line: serve, migrate, doctor, seed, worker, generate-fixtures, eval, export-reviews."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

API_ROOT = Path(__file__).resolve().parents[2]


def _alembic_config():  # type: ignore[no-untyped-def]
    """Alembic configuration for a checkout (apps/api) or for an installed package started from a directory
    that holds alembic.ini and alembic/ (the Docker image runs from /app, where both are copied)."""
    from alembic.config import Config

    for root in (API_ROOT, Path.cwd()):
        if (root / "alembic.ini").is_file() and (root / "alembic").is_dir():
            cfg = Config(str(root / "alembic.ini"))
            cfg.set_main_option("script_location", str(root / "alembic"))
            return cfg
    raise SystemExit(f"alembic.ini and alembic/ not found in {API_ROOT} or {Path.cwd()}; run from apps/api")


def cmd_migrate(_args: argparse.Namespace) -> int:
    from alembic import command

    command.upgrade(_alembic_config(), "head")
    print("migrations applied")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("bearcase.api.app:app", host=args.host, port=args.port, reload=args.reload, log_level="info")
    return 0


def cmd_seed(_args: argparse.Namespace) -> int:
    from bearcase.api.app import run_migrations
    from bearcase.db import session_scope
    from bearcase.seed import seed_for_demo_user

    run_migrations()
    t0 = time.time()
    with session_scope() as db:
        deal = seed_for_demo_user(db)
        deal_id = deal.id
    print(f"seeded Northstar HVAC deal {deal_id} in {time.time() - t0:.1f}s")
    return 0


def cmd_worker(args: argparse.Namespace) -> int:
    from bearcase.pipeline.jobs import poll_once

    print("worker polling for jobs (Ctrl+C to stop)")
    while True:
        if not poll_once():
            time.sleep(args.interval)


def cmd_generate_fixtures(args: argparse.Namespace) -> int:
    from bearcase.config import get_settings
    from bearcase.fixtures.generate import generate

    out = Path(args.out) if args.out else get_settings().fixtures_dir
    for p in generate(out):
        print(p)
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    if getattr(args, "reviews", None):
        # Agreement between the AI status and reviewer decisions over an exported review dataset; no seeding,
        # no model, no database: the file is the whole input.
        from bearcase.evals.run import review_agreement

        agreement = review_agreement(Path(args.reviews))
        if args.json:
            print(json.dumps(agreement, indent=2))
        else:
            print(agreement["summary_text"])
            print(
                "Note: this scores the AI statuses stored in the file against the reviewer decisions stored beside"
                " them. It describes past reviews; it does not run the current code. Use `bearcase eval` (fixtures)"
                " for the release check."
            )
        minimum = getattr(args, "min_agreement", None)
        rate = agreement.get("agreement_rate")
        if minimum is not None and agreement.get("judged", 0) and rate is not None and rate * 100 < minimum:
            print(f"Agreement {rate * 100:.1f}% is below the required {minimum}%.")
            return 1
        return 0
    from bearcase.evals.run import run_evals

    report = run_evals()
    print(json.dumps(report, indent=2) if args.json else report["summary_text"])
    return 0 if report["passed"] else 1


def cmd_export_reviews(args: argparse.Namespace) -> int:
    """Write the reviewed claims of one deal (or every deal) as JSON lines: the AI assessment beside the
    reviewer's decision and the cited evidence. Operator tooling over the configured database, so it is not
    owner-scoped the way the API export is."""
    from sqlalchemy import select

    from bearcase.api.routes.insights import review_dataset_rows, to_jsonl
    from bearcase.db import session_scope
    from bearcase.models import Deal

    out = Path(args.out)
    with session_scope() as db:
        if args.deal:
            try:
                deal_id = uuid.UUID(args.deal)
            except ValueError:
                raise SystemExit(f"--deal must be a deal id, got {args.deal!r}") from None
            deal = db.get(Deal, deal_id)
            if deal is None:
                raise SystemExit(f"deal {args.deal} not found")
            deals = [deal]
        else:
            deals = list(db.scalars(select(Deal).order_by(Deal.created_at, Deal.id)))
        rows = [row for deal in deals for row in review_dataset_rows(db, deal)]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(to_jsonl(rows), encoding="utf-8")
    scope = f"deal {args.deal}" if args.deal else f"{len(deals)} deal{'s' if len(deals) != 1 else ''}"
    print(f"wrote {len(rows)} reviewed claim{'s' if len(rows) != 1 else ''} from {scope} to {out}")
    return 0


# ---- doctor -----------------------------------------------------------------------------------------------

Status = Literal["ok", "warn", "fail"]


@dataclass
class DoctorRow:
    name: str
    status: Status
    detail: str


def _redact(text: str, secrets: list[str | None]) -> str:
    """Replace every configured secret that might appear in a driver's error text."""
    for secret in secrets:
        if secret and len(secret) >= 4:
            text = text.replace(secret, "***")
    return text


def _mb(n: int) -> str:
    return f"{n / (1024 * 1024):g} MB"


def doctor_rows() -> list[DoctorRow]:
    """Readiness checks for the configured environment. No row ever contains a key: providers are named by
    label and model id, and no check contacts a model provider (the chat backend is resolved from settings
    alone). The database and storage checks do touch the database and write one probe object."""
    from pydantic import ValidationError

    from bearcase.config import Settings, get_settings

    rows: list[DoctorRow] = []
    try:
        s = get_settings()
    except ValidationError as exc:
        problems = "; ".join(str(e.get("msg", "")).removeprefix("Value error, ") for e in exc.errors())
        rows.append(DoctorRow("settings", "fail", problems))
        return rows
    secrets: list[str | None] = [
        s.secret_key,
        s.anthropic_api_key,
        s.openai_api_key,
        s.gemini_api_key,
        s.groq_api_key,
        s.openrouter_api_key,
        s.chat_api_key,
        s.resend_api_key,
        s.stripe_secret_key,
        s.stripe_webhook_secret,
    ]

    rows.append(DoctorRow("env", "ok", s.env))

    # Database: reachable, and at the newest migration.
    from sqlalchemy import text
    from sqlalchemy.engine import make_url

    from bearcase.db import get_engine, reset_engine

    kind = "sqlite" if s.is_sqlite else "postgresql"
    try:
        url = make_url(s.database_url)
        secrets.append(url.password)
        where = url.render_as_string(hide_password=True)
    except Exception:
        where = kind
    try:
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory

        head = ScriptDirectory.from_config(_alembic_config()).get_current_head()
        reset_engine()
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
            current = MigrationContext.configure(conn).get_current_revision()
    except SystemExit as exc:
        rows.append(DoctorRow("database", "fail", str(exc)))
    except Exception as exc:
        rows.append(DoctorRow("database", "fail", f"{kind} not reachable ({where}): {_redact(str(exc), secrets)}"))
    else:
        if current == head:
            status: Status = "warn" if (s.is_sqlite and s.env == "production") else "ok"
            note = "; SQLite in production serves one process and lives on this instance's disk" if status == "warn" else ""
            rows.append(DoctorRow("database", status, f"{kind} reachable, migrated to {head}{note}"))
        else:
            hint = "run `bearcase migrate`" + (" (development mode also migrates on API start)" if s.env != "production" else "")
            rows.append(
                DoctorRow("database", "fail", f"{kind} reachable but at revision {current or 'none'}, head is {head}; {hint}")
            )

    # Storage: one probe object written, read back, and deleted.
    from bearcase.ingest.storage import get_storage

    place = f"local {s.storage_local_dir}" if s.storage_backend == "local" else f"s3 bucket {s.s3_bucket or '(unset)'}"
    try:
        storage = get_storage()
        key = f"doctor/{uuid.uuid4().hex}.txt"
        payload = b"bearcase doctor probe"
        storage.put(key, payload)
        readable = storage.exists(key) and storage.get(key) == payload
        storage.delete(key)
    except Exception as exc:
        rows.append(DoctorRow("storage", "fail", f"{place}: {_redact(str(exc), secrets)}"))
    else:
        if not readable:
            rows.append(DoctorRow("storage", "fail", f"{place}: the probe object could not be read back"))
        elif s.storage_backend == "local" and s.env == "production":
            rows.append(
                DoctorRow("storage", "warn", f"{place}, writable; on an ephemeral filesystem uploads vanish at the next deploy")
            )
        else:
            rows.append(DoctorRow("storage", "ok", f"{place}, writable"))

    # Secret key: never printed, only whether it is the checked-in default and how long it is.
    if s.secret_key == Settings.model_fields["secret_key"].default:
        rows.append(DoctorRow("secret key", "warn", "development default; fine locally, refused when BEARCASE_ENV=production"))
    elif len(s.secret_key) < 32:
        rows.append(DoctorRow("secret key", "warn", f"set, {len(s.secret_key)} characters; use 32 or more"))
    else:
        rows.append(DoctorRow("secret key", "ok", f"set, {len(s.secret_key)} characters"))

    # Chat: which backend answers, by label and model id only.
    from bearcase.chat.providers import MOCK_LABEL, resolve_chat_backend

    backend = resolve_chat_backend(s)
    if backend.kind == "mock":
        if s.chat_provider == "mock":
            rows.append(DoctorRow("chat", "ok", f"{backend.label} ({backend.model}); no live model by choice"))
        else:
            rows.append(DoctorRow("chat", "warn", f"{backend.label} ({backend.model}); no provider key found, so no live model"))
    elif not backend.ready:
        rows.append(DoctorRow("chat", "warn", f"{backend.label} is not ready ({backend.reason}); {MOCK_LABEL} answers instead"))
    else:
        detail = f"{backend.label} · {backend.model}"
        if backend.free_tier and backend.name != "ollama":
            detail += "; free tier: every user of this deployment shares one project's quota"
        rows.append(DoctorRow("chat", "ok", detail))

    # Extraction and reports.
    if s.ai_provider == "anthropic":
        has_key = bool(s.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
        if has_key:
            rows.append(DoctorRow("extraction", "ok", f"Anthropic Claude · {s.ai_model}"))
        else:
            rows.append(
                DoctorRow(
                    "extraction", "fail", f"Anthropic Claude · {s.ai_model}, but no ANTHROPIC_API_KEY; processing would fail"
                )
            )
    else:
        rows.append(DoctorRow("extraction", "ok", "Rule-based mock (rules-v1); no key needed"))

    # Abuse limits and quotas.
    if s.rate_limit_enabled:
        detail = f"on, {s.rate_limit_per_minute}/min per user (per client address before sign-in); in-process, so one API instance is assumed"
        if s.trust_proxy_headers:
            detail += "; X-Forwarded-For trusted"
        rows.append(DoctorRow("rate limits", "ok", detail))
    else:
        rows.append(DoctorRow("rate limits", "ok" if s.env == "test" else "warn", "off; model-calling routes are unmetered"))
    rows.append(
        DoctorRow(
            "quotas",
            "ok",
            f"{_mb(s.max_upload_bytes)} per upload, {s.max_documents_per_deal} documents per deal, "
            f"{_mb(s.max_storage_bytes_per_user)} per user, demo data kept {s.demo_retention_days} days",
        )
    )

    # Email: verification, reset, and invitation links; the console emailer only logs them.
    from bearcase.email import email_status

    email_state, email_detail = email_status(s)
    rows.append(DoctorRow("email", email_state, email_detail))  # type: ignore[arg-type]

    # Billing: the pilot checkout answers 503 until a Stripe key is set; the webhook also needs its secret.
    price = f"{s.pilot_price_cents / 100:,.2f} {s.pilot_currency.upper()}"
    if s.stripe_secret_key and s.stripe_webhook_secret:
        rows.append(DoctorRow("billing", "ok", f"Stripe Checkout, pilot {price}; webhook secret set"))
    elif s.stripe_secret_key:
        rows.append(
            DoctorRow(
                "billing",
                "warn",
                f"Stripe Checkout, pilot {price}; STRIPE_WEBHOOK_SECRET missing, so payments are never marked paid",
            )
        )
    else:
        rows.append(
            DoctorRow(
                "billing",
                "warn" if s.env == "production" else "ok",
                f"not configured (pilot {price}); /api/billing/checkout answers 503 until STRIPE_SECRET_KEY is set",
            )
        )
    rows.append(DoctorRow("chat budget", "ok", f"{s.chat_monthly_request_limit} assistant answers per user per calendar month"))

    # CORS: the browser's Origin never carries a trailing slash, and localhost is only right in development.
    origins = ", ".join(s.cors_origins) or "(none)"
    if any(o.endswith("/") for o in s.cors_origins):
        rows.append(DoctorRow("cors", "warn", f"{origins}; an origin with a trailing slash never matches"))
    elif s.env == "production" and any("localhost" in o or "127.0.0.1" in o for o in s.cors_origins):
        rows.append(DoctorRow("cors", "warn", f"{origins}; still a localhost origin in production"))
    else:
        rows.append(DoctorRow("cors", "ok", origins))

    # Jobs.
    runners = {
        "thread": "in-process, one worker thread",
        "sync": "inline, blocks the request (tests and seeding)",
        "poll": "queued for `bearcase worker`; make sure one is running",
    }
    job_status: Status = "warn" if (s.job_runner == "sync" and s.env != "test") else "ok"
    rows.append(DoctorRow("job runner", job_status, f"{s.job_runner}: {runners[s.job_runner]}"))
    return rows


def cmd_doctor(args: argparse.Namespace) -> int:
    from bearcase import __version__

    logging.getLogger("alembic").setLevel(logging.WARNING)  # plugin setup chatter would precede the table
    rows = doctor_rows()
    failures = sum(r.status == "fail" for r in rows)
    warnings = sum(r.status == "warn" for r in rows)
    if args.json:
        print(json.dumps({"version": __version__, "ready": failures == 0, "rows": [asdict(r) for r in rows]}, indent=2))
        return 1 if failures else 0
    print(f"BearCase doctor (bearcase {__version__})")
    width = max(len(r.name) for r in rows)
    for r in rows:
        print(f"  [{r.status:<4}] {r.name:<{width}}  {r.detail}")
    verdict = "Not ready: fix the failures above." if failures else "Ready."
    print(f"{failures} failure{'s' if failures != 1 else ''}, {warnings} warning{'s' if warnings != 1 else ''}. {verdict}")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="bearcase", description="BearCase AI API tooling")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="Apply database migrations").set_defaults(fn=cmd_migrate)
    d = sub.add_parser("doctor", help="Check the configured environment and print a readiness table (exit 1 on a failure)")
    d.add_argument("--json", action="store_true")
    d.set_defaults(fn=cmd_doctor)
    s = sub.add_parser("serve", help="Run the API server")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--reload", action="store_true")
    s.set_defaults(fn=cmd_serve)
    sub.add_parser("seed", help="Seed the fictional Northstar demo deal").set_defaults(fn=cmd_seed)
    w = sub.add_parser("worker", help="Poll and run queued jobs (for BEARCASE_JOB_RUNNER=poll)")
    w.add_argument("--interval", type=float, default=1.0)
    w.set_defaults(fn=cmd_worker)
    g = sub.add_parser("generate-fixtures", help="Regenerate the Northstar fixture files")
    g.add_argument("--out")
    g.set_defaults(fn=cmd_generate_fixtures)
    e = sub.add_parser("eval", help="Run the AI evaluation suite against ground truth")
    e.add_argument("--json", action="store_true")
    e.add_argument(
        "--reviews",
        metavar="FILE.jsonl",
        help="Instead of the suite, score AI status against reviewer decisions in a file from `bearcase export-reviews`",
    )
    e.add_argument("--min-agreement", type=float, metavar="PCT", help="With --reviews: exit 1 when agreement is below this percentage")
    e.set_defaults(fn=cmd_eval)
    x = sub.add_parser("export-reviews", help="Write reviewed claims (AI assessment, reviewer decision, evidence) as JSON lines")
    x.add_argument("--deal", help="Deal id; every deal when omitted")
    x.add_argument("--out", required=True, help="Output file path (.jsonl)")
    x.set_defaults(fn=cmd_export_reviews)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
