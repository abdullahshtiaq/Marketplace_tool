from pathlib import Path

import pytest

from flipwatch.config import FacebookConfig, KijijiConfig
from flipwatch.models import parse_mileage_km, parse_price, parse_year
from flipwatch.sources import SearchFilters
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


@pytest.mark.parametrize(
    "text,year,km",
    [
        ("2014 Honda Civic LX 182K km", 2014, 182000),
        ("2009 Tacoma, 245,000 kms, no rust", 2009, 245000),
        ("95k miles", None, 152888),
        ("1.8L engine, 5 km from downtown", None, None),
        ("Honda Civic", None, None),
    ],
)
def test_vehicle_details(text, year, km):
    assert parse_year(text) == year
    assert parse_mileage_km(text) == km


def test_kijiji_next_data():
    listings = kijiji.parse_search_page((FIXTURES / "kijiji_next_data.html").read_text())
    by_id = {l.id: l for l in listings}
    assert set(by_id) == {"1700000001", "1700000002", "1700000003"}
    civic = by_id["1700000001"]
    assert civic.price == 4500.0  # amount is in cents
    assert civic.year == 2014 and civic.mileage_km == 182000  # from attributes
    assert civic.location == "Toronto"
    assert civic.image_url.endswith("img1.jpg")
    assert civic.posted_at is not None
    assert "Moving" in civic.description
    assert by_id["1700000002"].price is None
    assert by_id["1700000002"].url.startswith("https://www.kijiji.ca/v-")
    assert by_id["1700000003"].price == 0.0


def test_kijiji_dom_fallback():
    listings = kijiji.parse_search_page((FIXTURES / "kijiji_dom.html").read_text())
    assert [l.id for l in listings] == ["1700000010", "1700000011"]
    corolla = listings[0].fill_vehicle_details()
    assert corolla.title == "2012 Toyota Corolla CE"
    assert corolla.price == 5900.0
    assert corolla.year == 2012 and corolla.mileage_km == 160000
    assert corolla.url == "https://www.kijiji.ca/v-cars-trucks/city-of-toronto/2012-toyota-corolla/1700000010"
    assert listings[1].price is None


def test_kijiji_url():
    cfg = KijijiConfig(location_slug="gta-greater-toronto-area", location_id=1700272)
    assert (
        kijiji.build_search_url(cfg, "Honda Civic!", 8000)
        == "https://www.kijiji.ca/b-cars-trucks/gta-greater-toronto-area/honda-civic/k0c174l1700272?sort=dateDesc&price=__8000"
    )
    cfg.category_slug = cfg.category_id = None
    assert "/b-gta-greater-toronto-area/civic/k0l1700272" in kijiji.build_search_url(cfg, "civic")


def test_facebook_cards():
    items = [
        {"href": "/marketplace/item/111/?ref=search", "text": "CA$4,500\n2014 Honda Civic LX\nToronto, ON\n182K km", "img": "a.jpg"},
        {"href": "/marketplace/item/111/?ref=dup", "text": "CA$4,500\n2014 Honda Civic LX\nToronto, ON"},
        {"href": "/marketplace/item/222/", "text": "CA$8,000CA$9,500\n2015 Toyota Corolla\nMississauga, ON\n95K miles"},
        {"href": "/marketplace/item/333/", "text": "Free\nScrap car"},
        {"href": "/marketplace/category/vehicles", "text": "Vehicles"},
        {"href": "/marketplace/item/444/", "text": ""},
    ]
    listings = facebook.parse_cards(items)
    assert [l.id for l in listings] == ["111", "222", "333"]
    assert listings[0].price == 4500.0
    assert listings[0].title == "2014 Honda Civic LX"
    assert listings[0].location == "Toronto, ON"
    assert listings[0].mileage_km == 182000
    assert listings[0].url == "https://www.facebook.com/marketplace/item/111/"
    assert listings[1].price == 8000.0 and listings[1].mileage_km == 152888
    assert listings[2].price == 0.0 and listings[2].location == "" and listings[2].mileage_km is None


def test_facebook_url():
    cfg = FacebookConfig(location="toronto", radius_km=100)
    url = facebook.build_search_url(cfg, "honda civic", SearchFilters(max_price=8000, min_year=2012, max_km=200000))
    assert url.startswith("https://www.facebook.com/marketplace/toronto/search/?query=honda+civic&sortBy=")
    for part in ("sortBy=creation_time_descend", "maxPrice=8000", "minYear=2012", "maxMileage=200000", "radius=100"):
        assert part in url
    assert "maxYear" not in url


def test_browse_all_urls():
    kcfg = KijijiConfig(location_slug="calgary", location_id=1700199)
    assert kijiji.build_search_url(kcfg, "") == "https://www.kijiji.ca/b-cars-trucks/calgary/c174l1700199?sort=dateDesc"
    url = facebook.build_search_url(FacebookConfig(location="calgary"), "", SearchFilters(max_price=6000))
    assert url.startswith("https://www.facebook.com/marketplace/calgary/vehicles?sortBy=creation_time_descend")
    assert "maxPrice=6000" in url and "query" not in url
