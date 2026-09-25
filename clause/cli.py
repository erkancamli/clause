"""Command line entry point."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from . import __version__


def _serve(args: argparse.Namespace) -> None:
    import os

    import uvicorn
    from .api.app import create_app
    from .api.security import Settings

    # Settings come from the environment so that a deployment is configured in
    # one root owned file rather than in a command line anyone can read from the
    # process table. The service refuses to start on a dangerous combination,
    # and that refusal should happen here, before the port is bound.
    settings = Settings.from_env()
    # Before anything else that might want to say something. --log-level is
    # uvicorn's own and governs its access and error loggers; this protocol's
    # lines are its own setting, because turning uvicorn down should not turn
    # the record of what the protocol did off. See telemetry.py.
    from .telemetry import configure as configure_logging

    level = configure_logging()
    trials = int(os.environ.get("CLAUSE_TRIALS", args.trials))
    # Rider calls the protocol over HTTP like everyone else, so it needs to know
    # which port this process ended up on.
    os.environ.setdefault("CLAUSE_PORT", str(args.port))

    def state(name: str, on: bool, danger: str) -> str:
        return f"  {name:10s} {'ON  ' + danger if on else 'off'}"

    print()
    print(f"  clause {__version__}")
    print(f"  protocol   http://{args.host}:{args.port}")
    print(f"  chain      {args.speed}x of Rialo's fifty millisecond blocks")
    print(f"  pricing    {trials:,} trials behind every capital figure")
    print()
    print(state("demo", settings.demo_endpoints, "(chain can be driven by hand)"))
    print(state("faucet", settings.faucet, "(new addresses are funded)"))
    print(state("docs", settings.public_docs, "(every route is listed)"))
    print(f"  {'log':10s} {level.lower()} (CLAUSE_LOG_LEVEL)")
    print(state(
        "rider", bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUSE_RIDER_LATCH")),
        "(" + ("through a Latch" if os.environ.get("CLAUSE_RIDER_LATCH") else "direct API key")
        + ("; can buy under a mandate" if os.environ.get("CLAUSE_RIDER_BUY_LATCH") else "; reads only") + ")",
    ))
    print(state("specimens", settings.specimens, "(stand in companies everywhere)"))
    print(state("direct buy", settings.direct_buy, "(home and vehicle cover without review)"))
    print(f"  origins    {', '.join(settings.allowed_origins) or 'none (same origin only)'}")
    print()

    uvicorn.run(
        create_app(
            trials=trials, speed=args.speed, seed=args.seed, settings=settings,
        ),
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        timeout_graceful_shutdown=5,
        # Behind nginx, and the client address is taken from the forwarded
        # header only when the operator has said there is a proxy in front.
        proxy_headers=os.environ.get("CLAUSE_BEHIND_PROXY") == "1",
        forwarded_allow_ips="127.0.0.1",
        server_header=False,
        date_header=True,
    )


def _quote(args: argparse.Namespace) -> None:
    import json

    from .pricing import PricingEngine
    from .protocol import Pool

    pool = Pool(engine=PricingEngine(trials=args.trials))
    pool.deposit("lp", args.capital)
    subject = json.loads(args.subject)
    quoted = pool.quote(
        peril_key=args.peril, subject=subject,
        limit=args.limit, term_days=args.term,
    )
    data = quoted.to_dict()
    print(f"  premium        {data['premium']:,.2f}")
    print(f"  expected loss  {data['expected_loss']:,.2f}")
    print(f"  risk load      {data['risk_load']:,.2f}")
    print(f"  running cost   {data['expense_load']:,.2f}")
    print(f"  rate on line   {data['rate_on_line'] * 100:.3f}%")
    print(f"  trigger chance {data['trigger_probability'] * 100:.3f}%")
    print(f"  diversification {data['diversification']}")
    for note in data["notes"]:
        print(f"    - {note}")


def _backup(args: argparse.Namespace) -> None:
    """Copy the book somewhere else, while the service is still running.

    The only mention of a backup anywhere in this project was one line of
    prose in a README. There was no command to run, so there was nothing for
    a cron line to call and nothing to rehearse a restore from -- and the
    book, the sealed documents and the simulated chain all live in the same
    directory, which means losing it loses everything at once.

    SQLite's own online backup is used rather than copying the file, because
    copying a database that is being written to produces a file that opens
    and is wrong. The sealed documents beside it are copied too: a book that
    refers to documents that are not there is not a restorable book.
    """
    import shutil
    import sqlite3
    import time as _time
    from pathlib import Path

    from .store import default_path

    source = Path(args.book) if args.book else default_path()
    if source is None:
        raise SystemExit(
            "no book to back up: set CLAUSE_STATE_DIR, or pass --book")
    if not source.exists():
        raise SystemExit(f"no book at {source}")

    stamp = _time.strftime("%Y%m%dT%H%M%SZ", _time.gmtime())
    into = Path(args.to) / f"clause-{stamp}"
    into.mkdir(parents=True, exist_ok=False)

    live = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    try:
        copy = sqlite3.connect(into / source.name)
        try:
            live.backup(copy)
        finally:
            copy.close()
    finally:
        live.close()

    kept = 0
    for name in ("documents", "sealed"):
        beside = source.parent / name
        if beside.is_dir():
            shutil.copytree(beside, into / name)
            kept += sum(1 for _ in (into / name).rglob("*") if _.is_file())

    size = (into / source.name).stat().st_size
    print(f"  book      {source}")
    print(f"  copied to {into / source.name} ({size / 1_048_576:.1f} MB)")
    print(f"  documents {kept} file(s)")
    print()
    print("  Restore by stopping the service, putting these back where they")
    print("  came from, and starting it. Rehearse that before you need it.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clause", description="Parametric cover that settles itself, on Rialo"
    )
    parser.add_argument("--version", action="version", version=f"clause {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the protocol and its interface")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--speed", type=float, default=1.0)
    serve.add_argument("--trials", type=int, default=12_000)
    serve.add_argument("--seed", type=int, default=20260917)
    serve.add_argument("--log-level", default="warning")
    serve.set_defaults(func=_serve)

    backup = sub.add_parser(
        "backup", help="copy the book and its documents somewhere safe")
    backup.add_argument("--to", required=True, help="a directory to write into")
    backup.add_argument("--book", default="", help="the sqlite file; default CLAUSE_STATE_DIR")
    backup.set_defaults(func=_backup)

    quote = sub.add_parser("quote", help="price one policy from the command line")
    quote.add_argument("peril", choices=["earthquake", "drought", "flight_delay", "vehicle_flood", "storm"])
    quote.add_argument("subject", help="JSON, for example '{\"location\":\"IST-KADIKOY\",\"radius_km\":50}'")
    quote.add_argument("--limit", type=float, default=100_000)
    quote.add_argument("--term", type=float, default=365)
    quote.add_argument("--capital", type=float, default=10_000_000)
    quote.add_argument("--trials", type=int, default=12_000)
    quote.set_defaults(func=_quote)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except KeyboardInterrupt:
        print()
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
