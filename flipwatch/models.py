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
    year: int | None = None
    mileage_km: int | None = None
    extra: dict = field(default_factory=dict)

    def fill_vehicle_details(self) -> "Listing":
        """Fill in year/mileage from the text when the site didn't give them."""
        text = f"{self.title} {self.description}"
        if self.year is None:
            self.year = parse_year(text)
        if self.mileage_km is None:
            self.mileage_km = parse_mileage_km(text)
        return self

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


_YEAR_RE = re.compile(r"(?<!\d)(19[5-9]\d|20[0-4]\d)(?!\d)")
_MILEAGE_RE = re.compile(
    r"(?<![\d.,])(\d{1,3}(?:[,.]\d{3})+|\d+(?:\.\d+)?)\s*(k|thousand)?\s*"
    r"(km|kms|kilometers|kilometres|mi|miles)\b",
    re.IGNORECASE,
)
_MILES_TO_KM = 1.609344


def parse_year(text: str | None) -> int | None:
    """Model year: the first plausible 4-digit year, e.g. "2014 Honda Civic"."""
    if not text:
        return None
    m = _YEAR_RE.search(text)
    return int(m.group(1)) if m else None


def parse_mileage_km(text: str | None) -> int | None:
    """Mileage like "180K km", "180,000 kms", "95k miles" -> kilometres."""
    if not text:
        return None
    for m in _MILEAGE_RE.finditer(text):
        number, thousands, unit = m.groups()
        value = float(re.sub(r"[,.](?=\d{3}\b)", "", number))
        if thousands:
            value *= 1000
        if unit.lower().startswith("mi"):
            value *= _MILES_TO_KM
        if value >= 100 or thousands:  # skip things like "5 km away"
            return int(round(value))
    return None
