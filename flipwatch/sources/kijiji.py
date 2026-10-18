from __future__ import annotations

import json
import re
from datetime import datetime
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup

from ..config import KijijiConfig
from ..models import Listing, parse_price
from . import SourceError

BASE_URL = "https://www.kijiji.ca"
_LISTING_ID_RE = re.compile(r"/(\d{6,})(?:[/?#]|$)")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def build_search_url(cfg: KijijiConfig, query: str, max_price: float | None = None) -> str:
    q = _slug(query)
    if cfg.category_slug and cfg.category_id is not None:
        path = f"/b-{cfg.category_slug}/{cfg.location_slug}/{q}/k0c{cfg.category_id}l{cfg.location_id}"
    else:
        path = f"/b-{cfg.location_slug}/{q}/k0l{cfg.location_id}"
    params = {"sort": "dateDesc"}
    if max_price is not None:
        params["price"] = f"__{int(max_price)}"
    return f"{BASE_URL}{path}?{urlencode(params)}"


def _parse_date(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _price_from_json(price) -> float | None:
    if isinstance(price, (int, float)):
        return float(price)
    if not isinstance(price, dict):
        return None
    if str(price.get("type", "")).upper() == "FREE":
        return 0.0
    amount = price.get("amount")
    if isinstance(amount, (int, float)):
        # Kijiji's GraphQL state stores amounts in cents.
        return amount / 100
    return None


def _walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _listing_from_json(d: dict) -> Listing | None:
    url = d.get("url") or d.get("seoUrl")
    title = d.get("title")
    if not isinstance(url, str) or not isinstance(title, str) or "/v-" not in url:
        return None
    listing_id = str(d.get("id") or "")
    if not listing_id.isdigit():
        m = _LISTING_ID_RE.search(url)
        if not m:
            return None
        listing_id = m.group(1)
    location = d.get("location")
    location_name = location.get("name", "") if isinstance(location, dict) else ""
    images = d.get("imageUrls") or []
    return Listing(
        source="kijiji",
        id=listing_id,
        title=title.strip(),
        price=_price_from_json(d.get("price")),
        url=urljoin(BASE_URL, url),
        location=location_name or "",
        description=(d.get("description") or "")[:1000],
        image_url=images[0] if images and isinstance(images[0], str) else None,
        posted_at=_parse_date(d.get("activationDate") or d.get("sortingDate")),
    )


def _from_next_data(soup: BeautifulSoup) -> list[Listing]:
    script = soup.find("script", id="__NEXT_DATA__")
    if script is None or not script.string:
        return []
    try:
        data = json.loads(script.string)
    except json.JSONDecodeError:
        return []
    listings: dict[str, Listing] = {}
    for node in _walk(data):
        listing = _listing_from_json(node)
        if listing and listing.id not in listings:
            listings[listing.id] = listing
    return list(listings.values())


def _from_dom(soup: BeautifulSoup) -> list[Listing]:
    listings: dict[str, Listing] = {}
    cards = soup.select('[data-testid="listing-card"], [data-listing-id]')
    for card in cards:
        link = card.select_one('a[data-testid="listing-link"], a[href*="/v-"]')
        if link is None:
            continue
        url = urljoin(BASE_URL, link.get("href", ""))
        listing_id = card.get("data-listingid") or card.get("data-listing-id")
        if not listing_id:
            m = _LISTING_ID_RE.search(url)
            if not m:
                continue
            listing_id = m.group(1)
        title_el = card.select_one('[data-testid="listing-title"], .title')
        price_el = card.select_one('[data-testid="listing-price"], .price')
        loc_el = card.select_one('[data-testid="listing-location"], .location')
        desc_el = card.select_one('[data-testid="listing-description"], .description')
        img = card.select_one("img")
        listings.setdefault(
            str(listing_id),
            Listing(
                source="kijiji",
                id=str(listing_id),
                title=(title_el or link).get_text(" ", strip=True),
                price=parse_price(price_el.get_text(" ", strip=True)) if price_el else None,
                url=url,
                location=loc_el.get_text(" ", strip=True) if loc_el else "",
                description=desc_el.get_text(" ", strip=True) if desc_el else "",
                image_url=img.get("src") if img else None,
            ),
        )
    return list(listings.values())


def parse_search_page(html: str) -> list[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    return _from_next_data(soup) or _from_dom(soup)


class KijijiSource:
    name = "kijiji"

    def __init__(self, cfg: KijijiConfig, session: requests.Session | None = None):
        self.cfg = cfg
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": cfg.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-CA,en;q=0.9",
            }
        )

    def search(self, query: str, max_price: float | None = None) -> list[Listing]:
        url = build_search_url(self.cfg, query, max_price)
        try:
            resp = self.session.get(url, timeout=self.cfg.timeout_seconds)
        except requests.RequestException as e:
            raise SourceError(f"kijiji request failed: {e}") from e
        if resp.status_code != 200:
            raise SourceError(f"kijiji returned HTTP {resp.status_code} for {url}")
        return parse_search_page(resp.text)

    def close(self) -> None:
        self.session.close()
