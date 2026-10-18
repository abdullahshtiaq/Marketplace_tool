from __future__ import annotations

import logging
import random
import time

from .config import Config, Watch
from .evaluator import evaluate, search_max_price
from .models import Listing
from .notifiers import Notifier, broadcast, format_alert
from .sources import Source, SourceError
from .store import Store, is_missing

log = logging.getLogger(__name__)


class Runner:
    def __init__(
        self,
        cfg: Config,
        store: Store,
        sources: dict[str, Source],
        notifiers: list[Notifier],
        sleep=time.sleep,
    ):
        self.cfg = cfg
        self.store = store
        self.sources = sources
        self.notifiers = notifiers
        self.sleep = sleep

    def run_forever(self) -> None:
        while True:
            started = time.monotonic()
            alerts = self.run_cycle()
            log.info("cycle done in %.0fs, %d alert(s)", time.monotonic() - started, alerts)
            self.sleep(self.cfg.poll_interval_seconds + random.uniform(0, self.cfg.jitter_seconds))

    def run_cycle(self) -> int:
        alerts = 0
        searches = [
            (watch, self.sources[name], query)
            for watch in self.cfg.watches
            for name in watch.sources
            if name in self.sources
            for query in watch.queries
        ]
        for i, (watch, source, query) in enumerate(searches):
            if i:
                self.sleep(self.cfg.request_delay_seconds * random.uniform(0.7, 1.5))
            try:
                listings = source.search(query, search_max_price(watch, self.cfg.deals))
            except SourceError as e:
                log.warning("%s search %r failed: %s", source.name, query, e)
                continue
            except Exception:
                log.exception("%s search %r crashed", source.name, query)
                continue
            scope = f"{source.name}|{watch.name}|{query}"
            silent = not self.cfg.alert_on_first_run and not self.store.is_primed(scope)
            for listing in listings:
                if self._handle(listing, watch, query, silent):
                    alerts += 1
            self.store.mark_primed(scope)
            log.debug("%s %r: %d listings%s", source.name, query, len(listings), " (priming)" if silent else "")
        return alerts

    def _handle(self, listing: Listing, watch: Watch, query: str, silent: bool) -> bool:
        prev_price = self.store.previous_price(listing, watch.name)
        self.store.record(listing, watch.name)
        if silent:
            return False

        price_drop_from = None
        if not is_missing(prev_price):
            dropped = prev_price is not None and listing.price is not None and listing.price < prev_price
            if not dropped:
                return False
            price_drop_from = prev_price

        verdict = evaluate(listing, watch, self.cfg.deals, query)
        if not verdict.is_deal:
            log.debug("skip %s %r: %s", listing.key, listing.title, verdict.reason)
            return False

        # The same listing can turn up under several watches/queries; alert once
        # unless the price has dropped since the last alert.
        last_alert = self.store.last_alert_price(listing)
        if not is_missing(last_alert) and not (
            last_alert is not None and listing.price is not None and listing.price < last_alert
        ):
            return False

        title, body = format_alert(listing, verdict, watch.name, price_drop_from)
        broadcast(self.notifiers, title, body, listing)
        self.store.mark_alerted(listing)
        return True
