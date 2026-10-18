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
    market_value: float | None = None
    value_basis: str = ""
    signals: list[str] = field(default_factory=list)


def _normalize(text: str) -> str:
    """Lowercase and strip accents so "Hyundaï" matches "hyundai"."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _contains(text: str, phrase: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(_normalize(phrase))}(?![a-z0-9])", text) is not None


def static_market_value(listing: Listing, watch: Watch) -> tuple[float | None, str]:
    """Value from the config: per-year table first, then a fixed market_value."""
    if listing.year is not None and listing.year in watch.market_value_by_year:
        return watch.market_value_by_year[listing.year], f"{listing.year} value"
    if isinstance(watch.market_value, (int, float)):
        return float(watch.market_value), "fixed value"
    return None, ""


def has_valuation(watch: Watch) -> bool:
    return watch.market_value is not None or bool(watch.market_value_by_year)


def net_resale(market_value: float, deals: DealSettings) -> float:
    return market_value * (1 - deals.selling_fee_pct) - deals.fixed_costs


def search_max_price(watch: Watch, deals: DealSettings) -> float | None:
    """Highest price worth looking at, used to pre-filter searches on the site."""
    candidates = []
    if watch.max_price is not None:
        candidates.append(watch.max_price)
    # Auto valuation needs to see the full price range to build comps, so it
    # only uses the explicit max_price.
    if not watch.auto_value:
        values = list(watch.market_value_by_year.values())
        if isinstance(watch.market_value, (int, float)):
            values.append(float(watch.market_value))
        if values:
            min_profit = watch.min_profit if watch.min_profit is not None else deals.min_profit
            best = net_resale(max(values), deals) - min_profit
            candidates.append(max(best / (1 + deals.purchase_tax_pct), 0))
    return min(candidates) if candidates else None


def filter_reason(listing: Listing, watch: Watch, deals: DealSettings, query: str | None = None) -> str | None:
    """Why this listing isn't the car the watch is after (ignoring price), or None."""
    text = _normalize(f"{listing.title} {listing.description}")

    for phrase in [*deals.exclude, *watch.exclude]:
        if _contains(text, phrase):
            return f"excluded word: {phrase!r}"

    if watch.match_query_terms and query:
        missing = [t for t in query.split() if len(t) > 1 and not _contains(text, t)]
        if missing:
            return f"missing query term(s): {', '.join(missing)}"
    missing = [t for t in watch.require_all if not _contains(text, t)]
    if missing:
        return f"missing required term(s): {', '.join(missing)}"
    if watch.require_any and not any(_contains(text, t) for t in watch.require_any):
        return "none of require_any present"

    # Unknown year/mileage passes; most car titles include the year anyway.
    if listing.year is not None:
        if watch.min_year is not None and listing.year < watch.min_year:
            return f"year {listing.year} < {watch.min_year}"
        if watch.max_year is not None and listing.year > watch.max_year:
            return f"year {listing.year} > {watch.max_year}"
    if watch.max_km is not None and listing.mileage_km is not None and listing.mileage_km > watch.max_km:
        return f"{listing.mileage_km:,} km > {watch.max_km:,} km"

    return None


def evaluate(
    listing: Listing,
    watch: Watch,
    deals: DealSettings,
    query: str | None = None,
    market_value: tuple[float | None, str] | None = None,
) -> Verdict:
    """Decide whether a listing is a possible flip.

    market_value is (value, basis) when the caller has already estimated it
    (e.g. from comparable listings); otherwise the watch's config is used.
    """
    reason = filter_reason(listing, watch, deals, query)
    if reason:
        return Verdict(False, reason)

    text = _normalize(f"{listing.title} {listing.description}")
    signals = [s for s in deals.signals if _contains(text, s)]

    price = listing.price
    if price is None:
        if watch.allow_no_price:
            return Verdict(True, "no price listed", signals=signals)
        return Verdict(False, "no price listed")

    min_price = watch.min_price if watch.min_price is not None else deals.min_price
    if price < min_price:
        return Verdict(False, f"price ${price:,.0f} below min ${min_price:,.0f} (likely placeholder)")
    if watch.max_price is not None and price > watch.max_price:
        return Verdict(False, f"price ${price:,.0f} above max ${watch.max_price:,.0f}")

    value, basis = market_value if market_value is not None else static_market_value(listing, watch)
    if value is None:
        if has_valuation(watch):
            return Verdict(False, "no market value estimate for this listing yet", signals=signals)
        # No valuation configured: anything under max_price that passed the filters is worth a look.
        return Verdict(True, "under max price", signals=signals)

    cost = price * (1 + deals.purchase_tax_pct) + deals.fixed_costs
    profit = value * (1 - deals.selling_fee_pct) - cost
    roi = profit / cost if cost > 0 else float("inf")
    min_profit = watch.min_profit if watch.min_profit is not None else deals.min_profit
    min_roi = watch.min_roi if watch.min_roi is not None else deals.min_roi
    common = dict(est_profit=profit, roi=roi, market_value=value, value_basis=basis, signals=signals)
    if profit < min_profit:
        return Verdict(False, f"est. profit ${profit:,.0f} < ${min_profit:,.0f}", **common)
    if roi < min_roi:
        return Verdict(False, f"ROI {roi:.0%} < {min_roi:.0%}", **common)
    return Verdict(True, "flip margin", **common)
