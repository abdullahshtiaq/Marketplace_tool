from pathlib import Path

import pytest

from flipwatch.config import FacebookConfig, KijijiConfig
from flipwatch.models import parse_price
from flipwatch.sources import facebook, kijiji

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("CA$1,200", 1200.0),
        ("$45.50", 45.5),
        ("C$80$100", 80.0),
        ("Free", 0.0),
        ("Please contact", None),
        ("", None),
        ("250", 250.0),
    ],
)
def test_parse_price(text, expected):
    assert parse_price(text) == expected


def test_kijiji_next_data():
    listings = kijiji.parse_search_page((FIXTURES / "kijiji_next_data.html").read_text())
    by_id = {l.id: l for l in listings}
    assert set(by_id) == {"1700000001", "1700000002", "1700000003"}
    binder = by_id["1700000001"]
    assert binder.price == 40.0  # amount is in cents
    assert binder.location == "Toronto"
    assert binder.image_url.endswith("img1.jpg")
    assert binder.posted_at is not None
    assert "Moving" in binder.description
    assert by_id["1700000002"].price is None
    assert by_id["1700000002"].url.startswith("https://www.kijiji.ca/v-")
    assert by_id["1700000003"].price == 0.0


def test_kijiji_dom_fallback():
    listings = kijiji.parse_search_page((FIXTURES / "kijiji_dom.html").read_text())
    assert [l.id for l in listings] == ["1700000010", "1700000011"]
    gpu = listings[0]
    assert gpu.title == "RTX 3080 10GB - works great"
    assert gpu.price == 300.0
    assert gpu.url == "https://www.kijiji.ca/v-video-cards/city-of-toronto/rtx-3080-10gb/1700000010"
    assert listings[1].price is None


def test_kijiji_url():
    cfg = KijijiConfig(location_slug="gta-greater-toronto-area", location_id=1700272)
    assert (
        kijiji.build_search_url(cfg, "Pokemon Cards!", 60)
        == "https://www.kijiji.ca/b-gta-greater-toronto-area/pokemon-cards/k0l1700272?sort=dateDesc&price=__60"
    )
    cfg.category_slug, cfg.category_id = "buy-sell", 10
    assert "/b-buy-sell/gta-greater-toronto-area/charizard/k0c10l1700272" in kijiji.build_search_url(cfg, "charizard")


def test_facebook_cards():
    items = [
        {"href": "/marketplace/item/111/?ref=search", "text": "CA$40\nPokemon card binder\nToronto, ON", "img": "a.jpg"},
        {"href": "/marketplace/item/111/?ref=dup", "text": "CA$40\nPokemon card binder\nToronto, ON"},
        {"href": "/marketplace/item/222/", "text": "CA$80CA$120\nRTX 3080\nMississauga, ON"},
        {"href": "/marketplace/item/333/", "text": "Free\nBox of hockey cards"},
        {"href": "/marketplace/category/toys", "text": "Toys"},
        {"href": "/marketplace/item/444/", "text": ""},
    ]
    listings = facebook.parse_cards(items)
    assert [l.id for l in listings] == ["111", "222", "333"]
    assert listings[0].price == 40.0
    assert listings[0].title == "Pokemon card binder"
    assert listings[0].location == "Toronto, ON"
    assert listings[0].url == "https://www.facebook.com/marketplace/item/111/"
    assert listings[1].price == 80.0
    assert listings[2].price == 0.0 and listings[2].location == ""


def test_facebook_url():
    cfg = FacebookConfig(location="toronto", radius_km=60)
    url = facebook.build_search_url(cfg, "rtx 3080", 400)
    assert url.startswith("https://www.facebook.com/marketplace/toronto/search/?query=rtx+3080")
    assert "sortBy=creation_time_descend" in url and "maxPrice=400" in url and "radius=60" in url
