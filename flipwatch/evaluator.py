from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .config import DealSettings, Watch
from .models import Listing


@dataclass
class Verdict:
    is_deal: bool
    reason: str
    est_profit: float | None = None
    roi: float | None = None
    signals: list[str] = field(default_factory=list)


def _normalize(text: str) -> str:
    """Lowercase and strip accents so "Pokémon" matches "pokemon"."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _contains(text: str, phrase: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(_normalize(phrase))}(?![a-z0-9])", text) is not None


def net_resale(watch: Watch, deals: DealSettings) -> float | None:
    if watch.market_value is None:
        return None
    return watch.market_value * (1 - deals.selling_fee_pct) - deals.fixed_costs


def search_max_price(watch: Watch, deals: DealSettings) -> float | None:
    """Highest price worth looking at, used to pre-filter searches on the site."""
    candidates = []
    if watch.max_price is not None:
        candidates.append(watch.max_price)
    net = net_resale(watch, deals)
    if net is not None:
        min_profit = watch.min_profit if watch.min_profit is not None else deals.min_profit
        candidates.append(max(net - min_profit, 0))
    return min(candidates) if candidates else None


def evaluate(listing: Listing, watch: Watch, deals: DealSettings, query: str | None = None) -> Verdict:
    text = _normalize(f"{listing.title} {listing.description}")

    for phrase in [*deals.exclude, *watch.exclude]:
        if _contains(text, phrase):
            return Verdict(False, f"excluded word: {phrase!r}")

    if watch.match_query_terms and query:
        missing = [t for t in query.split() if len(t) > 1 and not _contains(text, t)]
        if missing:
            return Verdict(False, f"missing query term(s): {', '.join(missing)}")
    missing = [t for t in watch.require_all if not _contains(text, t)]
    if missing:
        return Verdict(False, f"missing required term(s): {', '.join(missing)}")
    if watch.require_any and not any(_contains(text, t) for t in watch.require_any):
        return Verdict(False, "none of require_any present")

    signals = [s for s in deals.signals if _contains(text, s)]

    price = listing.price
    if price is None:
        if watch.allow_no_price:
            return Verdict(True, "no price listed", signals=signals)
        return Verdict(False, "no price listed")

    min_price = watch.min_price if watch.min_price is not None else deals.min_price
    if price < min_price:
        return Verdict(False, f"price ${price:.0f} below min ${min_price:.0f} (likely placeholder)")
    if watch.max_price is not None and price > watch.max_price:
        return Verdict(False, f"price ${price:.0f} above max ${watch.max_price:.0f}")

    net = net_resale(watch, deals)
    if net is None:
        # No market value: anything under max_price that passed the filters is worth a look.
        return Verdict(True, "under max price", signals=signals)

    profit = net - price
    roi = profit / price if price > 0 else float("inf")
    min_profit = watch.min_profit if watch.min_profit is not None else deals.min_profit
    min_roi = watch.min_roi if watch.min_roi is not None else deals.min_roi
    if profit < min_profit:
        return Verdict(False, f"est. profit ${profit:.0f} < ${min_profit:.0f}", profit, roi, signals)
    if roi < min_roi:
        return Verdict(False, f"ROI {roi:.0%} < {min_roi:.0%}", profit, roi, signals)
    return Verdict(True, "flip margin", profit, roi, signals)
