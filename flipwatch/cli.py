from __future__ import annotations

import argparse
import logging
import sys

from .config import ConfigError, load_config
from .notifiers import broadcast, build_notifiers
from .runner import Runner
from .store import Store


def _build_sources(cfg, only: list[str] | None):
    sources = {}
    wanted = set(only) if only else None
    if cfg.kijiji.enabled and (wanted is None or "kijiji" in wanted):
        from .sources.kijiji import KijijiSource

        sources["kijiji"] = KijijiSource(cfg.kijiji)
    if cfg.facebook.enabled and (wanted is None or "facebook" in wanted):
        from .sources.facebook import FacebookSource

        sources["facebook"] = FacebookSource(cfg.facebook)
    return sources


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="flipwatch", description="Alerts for underpriced listings on Kijiji and Facebook Marketplace.")
    parser.add_argument("-c", "--config", default="config.yaml")
    parser.add_argument("-v", "--verbose", action="store_true", help="log every listing considered")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="watch continuously and alert on flips")
    run.add_argument("--once", action="store_true", help="run a single scan and exit")
    run.add_argument("--source", action="append", choices=["kijiji", "facebook"], help="limit to a source")
    sub.add_parser("fb-login", help="open a browser to log in to Facebook once")
    sub.add_parser("test-notify", help="send a test alert to every configured channel")

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    for noisy in ("urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2

    if args.command == "fb-login":
        from .sources.facebook import interactive_login

        interactive_login(cfg.facebook)
        return 0

    notifiers = build_notifiers(cfg.notify)
    if args.command == "test-notify":
        broadcast(notifiers, "flipwatch test", "If you can read this, alerts are working.")
        return 0

    sources = _build_sources(cfg, args.source)
    if not sources:
        print("no sources enabled (check kijiji.enabled / facebook.enabled)", file=sys.stderr)
        return 2
    store = Store(cfg.db_path)
    runner = Runner(cfg, store, sources, notifiers)
    try:
        if args.once:
            runner.run_cycle()
        else:
            runner.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for s in sources.values():
            s.close()
        store.close()
    return 0
