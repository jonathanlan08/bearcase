"""BearCase command line: serve, migrate, seed, worker, generate-fixtures, eval."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]


def cmd_migrate(_args: argparse.Namespace) -> int:
    from bearcase.api.app import run_migrations

    run_migrations()
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
    from bearcase.evals.run import run_evals

    report = run_evals()
    print(json.dumps(report, indent=2) if args.json else report["summary_text"])
    return 0 if report["passed"] else 1


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="bearcase", description="BearCase AI API tooling")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="Apply database migrations").set_defaults(fn=cmd_migrate)
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
    e.set_defaults(fn=cmd_eval)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
