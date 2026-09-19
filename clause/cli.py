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
