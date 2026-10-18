from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Words that almost always mean the listing isn't a car you can buy and flip.
DEFAULT_EXCLUDES = [
    "wtb",
    "looking for",
    "iso",
    "want to buy",
    "trade only",
    "trades only",
    "lease takeover",
    "lease transfer",
    "take over lease",
    "rental",
    "for rent",
    "parts only",
    "for parts",
    "parting out",
    "part out",
    "salvage",
    "no ownership",
    "no papers",
    # dealer ads - rarely priced to flip
    "financing available",
    "we finance",
    "all credit",
    "omvic",
    "plus hst",
    "+ hst",
]

# Words that hint the seller wants it gone fast, or the car needs a cheap fix.
DEFAULT_SIGNALS = [
    "as is",
    "as-is",
    "needs safety",
    "no safety",
    "must go",
    "must sell",
    "moving",
    "quick sale",
    "need gone",
    "obo",
    "estate",
    "one owner",
    "low km",
    "no rust",
    "check engine",
    "needs battery",
    "needs tlc",
    "mechanic special",
    "runs and drives",
    "winter tires",
]


@dataclass
class DealSettings:
    selling_fee_pct: float = 0.0  # Kijiji/Marketplace are free for private sellers
    # Safety certificate, detailing, small repairs buffer, plates, gas...
    fixed_costs: float = 600.0
    # Sales tax you pay when buying privately (Ontario charges 13% RST).
    purchase_tax_pct: float = 0.0
    min_profit: float = 1000.0
    min_roi: float = 0.15  # profit / total cost (price + tax + fixed_costs)
    min_price: float = 500.0  # ignores "$1" / "$123" placeholder prices
    # market_value: auto -> resale estimate = median comparable asking price * this
    auto_resale_pct: float = 0.90
    auto_min_comps: int = 5
    auto_comp_days: int = 30
    auto_year_window: int = 1  # compare against cars within +/- this many model years
    exclude: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDES))
    signals: list[str] = field(default_factory=lambda: list(DEFAULT_SIGNALS))


@dataclass
class Watch:
    name: str
    queries: list[str]
    sources: list[str] = field(default_factory=lambda: ["kijiji", "facebook"])
    # What you can realistically resell it for: a number, or "auto" to use the
    # median asking price of comparable listings flipwatch has seen.
    market_value: float | str | None = None
    # Per-model-year resale values, e.g. {2012: 6500, 2013: 7500}; wins over market_value.
    market_value_by_year: dict[int, float] = field(default_factory=dict)
    max_price: float | None = None
    min_price: float | None = None
    min_year: int | None = None
    max_year: int | None = None
    max_km: int | None = None
    min_profit: float | None = None
    min_roi: float | None = None
    require_all: list[str] = field(default_factory=list)
    require_any: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    # Require every word of the search query to appear in the listing text,
    # because both sites pad results with loosely related listings.
    match_query_terms: bool = True
    allow_no_price: bool = False

    @property
    def auto_value(self) -> bool:
        return isinstance(self.market_value, str) and self.market_value.lower() == "auto"


@dataclass
class KijijiConfig:
    enabled: bool = True
    # From a Kijiji search URL: /b-<location_slug>/.../k0l<location_id>
    location_slug: str = "canada"
    location_id: int = 0
    # Cars & Trucks category; set both to null to search all of Kijiji.
    category_slug: str | None = "cars-trucks"
    category_id: int | None = 174
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
    )
    timeout_seconds: float = 20.0


@dataclass
class FacebookConfig:
    enabled: bool = False
    # From a Marketplace URL: facebook.com/marketplace/<location>/...
    location: str = "toronto"
    radius_km: int | None = None
    days_since_listed: int = 1
    profile_dir: str = ".fb-profile"
    headless: bool = True
    scrolls: int = 2
    timeout_seconds: float = 30.0


@dataclass
class NotifyConfig:
    console: bool = True
    ntfy_topic: str | None = None
    ntfy_server: str = "https://ntfy.sh"
    discord_webhook: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None


@dataclass
class Config:
    watches: list[Watch]
    poll_interval_seconds: float = 180
    jitter_seconds: float = 30
    request_delay_seconds: float = 4  # pause between individual searches
    db_path: str = "flipwatch.db"
    # On the very first scan of a search, record what's already listed
    # without alerting, so you only hear about *new* listings.
    alert_on_first_run: bool = False
    deals: DealSettings = field(default_factory=DealSettings)
    kijiji: KijijiConfig = field(default_factory=KijijiConfig)
    facebook: FacebookConfig = field(default_factory=FacebookConfig)
    notify: NotifyConfig = field(default_factory=NotifyConfig)


class ConfigError(ValueError):
    pass


def _expand(value: Any) -> Any:
    """Expand ${ENV_VAR} references so secrets can stay out of the file."""
    if isinstance(value, str):
        expanded = os.path.expandvars(value)
        return None if expanded.startswith("${") else expanded
    if isinstance(value, list):
        return [_expand(v) for v in value]
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    return value


def _build(cls, data: dict | None, where: str):
    data = data or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{where}: expected a mapping")
    names = {f.name for f in dataclasses.fields(cls)}
    unknown = set(data) - names
    if unknown:
        raise ConfigError(f"{where}: unknown option(s) {', '.join(sorted(unknown))}")
    try:
        return cls(**data)
    except TypeError as e:
        raise ConfigError(f"{where}: {e}") from e


def parse_config(raw: dict) -> Config:
    raw = _expand(raw or {})
    watches_raw = raw.pop("watches", None)
    if not watches_raw:
        raise ConfigError("config needs at least one entry under 'watches'")
    watches = []
    for i, w in enumerate(watches_raw):
        watch = _build(Watch, w, f"watches[{i}]")
        if isinstance(watch.queries, str):
            watch.queries = [watch.queries]
        if not watch.queries:
            raise ConfigError(f"watches[{i}] ({watch.name}): needs at least one query")
        if isinstance(watch.market_value, str) and not watch.auto_value:
            raise ConfigError(f"watches[{i}] ({watch.name}): market_value must be a number or 'auto'")
        watch.market_value_by_year = {int(y): float(v) for y, v in (watch.market_value_by_year or {}).items()}
        watches.append(watch)

    sections = {
        "deals": DealSettings,
        "kijiji": KijijiConfig,
        "facebook": FacebookConfig,
        "notify": NotifyConfig,
    }
    built = {key: _build(cls, raw.pop(key, None), key) for key, cls in sections.items()}
    cfg = _build(Config, {**raw, "watches": watches, **built}, "config")
    return cfg


def load_config(path: str | Path) -> Config:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"config file not found: {path} (copy config.example.yaml to start)")
    with path.open(encoding="utf-8") as f:
        return parse_config(yaml.safe_load(f))
