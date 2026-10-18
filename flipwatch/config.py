from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Words that almost always mean the listing isn't a real, flippable item.
DEFAULT_EXCLUDES = [
    "wtb",
    "looking for",
    "iso",
    "buying",
    "want to buy",
    "fake",
    "proxy",
    "proxies",
    "custom",
    "orica",
    "replica",
    "reprint",
    "repro",
    "broken",
    "for parts",
    "not working",
    "trade only",
    "trades only",
]

# Words that hint a seller doesn't know (or care about) what they have.
DEFAULT_SIGNALS = [
    "lot",
    "collection",
    "binder",
    "bulk",
    "old cards",
    "childhood",
    "grandpa",
    "estate",
    "moving",
    "must go",
    "quick sale",
    "need gone",
    "obo",
    "sealed",
    "1st edition",
    "first edition",
    "psa",
    "bgs",
    "cgc",
    "graded",
]


@dataclass
class DealSettings:
    selling_fee_pct: float = 0.13  # marketplace + payment fees when you resell
    fixed_costs: float = 5.0  # shipping supplies, gas, sleeves, etc.
    min_profit: float = 30.0
    min_roi: float = 0.30  # profit / purchase price
    min_price: float = 5.0  # ignores "$1" placeholder prices
    exclude: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDES))
    signals: list[str] = field(default_factory=lambda: list(DEFAULT_SIGNALS))


@dataclass
class Watch:
    name: str
    queries: list[str]
    sources: list[str] = field(default_factory=lambda: ["kijiji", "facebook"])
    # What you can realistically resell it for (e.g. recent eBay sold average).
    market_value: float | None = None
    max_price: float | None = None
    min_price: float | None = None
    min_profit: float | None = None
    min_roi: float | None = None
    require_all: list[str] = field(default_factory=list)
    require_any: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    # Require every word of the search query to appear in the listing text,
    # because both sites pad results with loosely related listings.
    match_query_terms: bool = True
    allow_no_price: bool = False


@dataclass
class KijijiConfig:
    enabled: bool = True
    # From a Kijiji search URL: /b-<location_slug>/.../k0l<location_id>
    location_slug: str = "canada"
    location_id: int = 0
    # Optional, e.g. category_slug "buy-sell", category_id 10
    category_slug: str | None = None
    category_id: int | None = None
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
