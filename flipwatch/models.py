from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Listing:
    source: str
    id: str
    title: str
    price: float | None
    url: str
    location: str = ""
    description: str = ""
    image_url: str | None = None
    posted_at: datetime | None = None
    extra: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.id}"


_PRICE_RE = re.compile(r"(?:CA\$|C\$|CAD\s*|\$)\s*(\d[\d,]*(?:\.\d{1,2})?)", re.IGNORECASE)
_BARE_NUMBER_RE = re.compile(r"^\s*(\d[\d,]*(?:\.\d{1,2})?)\s*$")


def parse_price(text: str | None) -> float | None:
    """Parse a displayed price like "CA$1,200", "$45.00" or "Free".

    Returns None when no price is shown (e.g. "Please contact", "Swap/Trade").
    When several prices appear (Facebook shows "$80$100" for a price drop),
    the first one is the current price.
    """
    if not text:
        return None
    if re.search(r"\bfree\b", text, re.IGNORECASE):
        return 0.0
    m = _PRICE_RE.search(text) or _BARE_NUMBER_RE.match(text)
    if not m:
        return None
    return float(m.group(1).replace(",", ""))
