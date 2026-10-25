"""Facebook Marketplace via a real (Playwright-driven) Chromium session.

Marketplace search requires being logged in, so this uses a persistent browser
profile: run `python -m flipwatch fb-login` once, log in by hand, and the
watcher reuses those cookies afterwards.
"""

from __future__ import annotations

import re
from urllib.parse import urlencode

from ..config import FacebookConfig
from ..models import Listing, parse_mileage_km, parse_price
from . import SearchFilters, SourceError

BASE_URL = "https://www.facebook.com"
_ITEM_ID_RE = re.compile(r"/marketplace/item/(\d+)")
_PRICE_LINE_RE = re.compile(r"^(?:(?:CA\$|C\$|\$)\s*\d[\d,]*(?:\.\d{1,2})?\s*)+$|^free$", re.IGNORECASE)

# innerText loses its line breaks for cards scrolled off screen, so join the
# text of each innermost element instead.
_EXTRACT_JS = """
els => els.map(e => ({
  href: e.getAttribute('href'),
  text: Array.from(e.querySelectorAll('span, div'))
    .filter(n => n.children.length === 0 && n.textContent.trim())
    .map(n => n.textContent.trim())
    .join('\\n') || e.innerText,
  img: (e.querySelector('img') || {}).src || null,
}))
"""


def build_search_url(cfg: FacebookConfig, query: str, filters: SearchFilters | None = None) -> str:
    filters = filters or SearchFilters()
    params = {
        "sortBy": "creation_time_descend",
        "daysSinceListed": cfg.days_since_listed,
        "exact": "false",
    }
    if filters.max_price is not None:
        params["maxPrice"] = int(filters.max_price)
    if filters.min_year is not None:
        params["minYear"] = filters.min_year
    if filters.max_year is not None:
        params["maxYear"] = filters.max_year
    if filters.max_km is not None:
        params["maxMileage"] = filters.max_km
    if cfg.radius_km:
        params["radius"] = cfg.radius_km
    if not query:  # empty query: browse every new vehicle listing
        return f"{BASE_URL}/marketplace/{cfg.location}/vehicles?{urlencode(params)}"
    return f"{BASE_URL}/marketplace/{cfg.location}/search/?{urlencode({'query': query, **params})}"


def parse_cards(items: list[dict]) -> list[Listing]:
    """Turn raw result-card anchors ({href, text, img}) into listings.

    A card's visible text is, line by line: optional badges ("Just listed"),
    current price (optionally followed by the old price on a price drop),
    title, location and, for vehicles, mileage ("180K km").
    """
    listings: dict[str, Listing] = {}
    for item in items:
        m = _ITEM_ID_RE.search(item.get("href") or "")
        if not m or m.group(1) in listings:
            continue
        lines = [ln.strip() for ln in (item.get("text") or "").split("\n") if ln.strip()]
        # Drop badges before the price, e.g. "Just listed".
        first_price = next((i for i, ln in enumerate(lines[:3]) if _PRICE_LINE_RE.match(ln)), 0)
        lines = lines[first_price:]
        price_lines = []
        while lines and _PRICE_LINE_RE.match(lines[0]):
            price_lines.append(lines.pop(0))
        if not lines:
            continue
        listing_id = m.group(1)
        listings[listing_id] = Listing(
            source="facebook",
            id=listing_id,
            title=lines[0],
            price=parse_price(price_lines[0]) if price_lines else None,
            url=f"{BASE_URL}/marketplace/item/{listing_id}/",
            location=lines[1] if len(lines) > 1 else "",
            image_url=item.get("img"),
            mileage_km=next((km for ln in lines[2:] if (km := parse_mileage_km(ln))), None),
        )
    return list(listings.values())


def _launch(cfg: FacebookConfig, headless: bool):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise SourceError(
            "Facebook needs Playwright: pip install playwright && playwright install chromium"
        ) from e
    pw = sync_playwright().start()
    ctx = pw.chromium.launch_persistent_context(
        cfg.profile_dir,
        headless=headless,
        viewport={"width": 1280, "height": 900},
        locale="en-CA",
    )
    return pw, ctx


def interactive_login(cfg: FacebookConfig) -> None:
    pw, ctx = _launch(cfg, headless=False)
    try:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(f"{BASE_URL}/login")
        input("Log in to Facebook in the opened browser, then press Enter here... ")
    finally:
        ctx.close()
        pw.stop()


class FacebookSource:
    name = "facebook"

    def __init__(self, cfg: FacebookConfig):
        self.cfg = cfg
        self._pw = None
        self._ctx = None
        self._page = None

    def _ensure_page(self):
        if self._page is None:
            self._pw, self._ctx = _launch(self.cfg, headless=self.cfg.headless)
            self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        return self._page

    def search(self, query: str, filters: SearchFilters) -> list[Listing]:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        page = self._ensure_page()
        timeout_ms = self.cfg.timeout_seconds * 1000
        try:
            page.goto(build_search_url(self.cfg, query, filters), wait_until="domcontentloaded", timeout=timeout_ms)
            if "/login" in page.url or "checkpoint" in page.url:
                raise SourceError("not logged in to Facebook; run: python -m flipwatch fb-login")
            try:
                page.wait_for_selector('a[href*="/marketplace/item/"]', timeout=timeout_ms)
            except PlaywrightTimeout:
                return []  # no results for this search
            for _ in range(self.cfg.scrolls):
                page.mouse.wheel(0, 2500)
                page.wait_for_timeout(1200)
            items = page.eval_on_selector_all('a[href*="/marketplace/item/"]', _EXTRACT_JS)
        except PlaywrightError as e:
            self.close()  # start fresh next time
            raise SourceError(f"facebook browser error: {e}") from e
        return parse_cards(items)

    def close(self) -> None:
        try:
            if self._ctx is not None:
                self._ctx.close()
            if self._pw is not None:
                self._pw.stop()
        except Exception:
            pass
        finally:
            self._pw = self._ctx = self._page = None
