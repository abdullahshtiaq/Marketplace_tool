from flipwatch.config import DealSettings, Watch
from flipwatch.evaluator import evaluate, search_max_price
from flipwatch.models import Listing


def make(title, price, description="", year=None, km=None):
    l = Listing("kijiji", "1", title, price, "https://example.com/v-1", description=description,
                year=year, mileage_km=km)
    return l.fill_vehicle_details()


DEALS = DealSettings(fixed_costs=500, purchase_tax_pct=0.13, min_profit=1000, min_roi=0.15, min_price=500)
Q = "honda civic"


def test_flip_margin_with_tax_and_costs():
    watch = Watch(name="civic", queries=[Q], market_value=9000)
    v = evaluate(make("2014 Honda Civic", 6000), watch, DEALS, Q)
    cost = 6000 * 1.13 + 500
    assert v.is_deal
    assert v.est_profit == 9000 - cost
    assert v.roi == (9000 - cost) / cost
    assert not evaluate(make("2014 Honda Civic", 7000), watch, DEALS, Q).is_deal  # 9000 - 8410 = 590


def test_value_by_year():
    watch = Watch(name="civic", queries=[Q], market_value_by_year={2012: 6000, 2016: 12000})
    assert evaluate(make("2016 Honda Civic", 8000), watch, DEALS, Q).is_deal
    assert not evaluate(make("2012 Honda Civic", 8000), watch, DEALS, Q).is_deal
    v = evaluate(make("2014 Honda Civic", 3000), watch, DEALS, Q)  # no value for 2014
    assert not v.is_deal and "no market value" in v.reason


def test_supplied_market_value_wins():
    watch = Watch(name="civic", queries=[Q], market_value="auto")
    assert not evaluate(make("2014 Honda Civic", 4000), watch, DEALS, Q).is_deal  # no comps yet
    v = evaluate(make("2014 Honda Civic", 4000), watch, DEALS, Q, (9000, "comps"))
    assert v.is_deal and v.value_basis == "comps"


def test_year_and_mileage_filters():
    watch = Watch(name="civic", queries=[Q], min_year=2012, max_year=2016, max_km=200000, max_price=8000)
    assert evaluate(make("2014 Honda Civic 150k km", 5000), watch, DEALS, Q).is_deal
    assert not evaluate(make("2009 Honda Civic", 5000), watch, DEALS, Q).is_deal
    assert not evaluate(make("2018 Honda Civic", 5000), watch, DEALS, Q).is_deal
    assert not evaluate(make("2014 Honda Civic", 5000, "260,000 km"), watch, DEALS, Q).is_deal
    assert evaluate(make("Honda Civic", 5000), watch, DEALS, Q).is_deal  # unknown year passes


def test_filters():
    watch = Watch(name="civic", queries=[Q], max_price=8000, exclude=["type r"])
    assert not evaluate(make("WTB Honda Civic", 5000), watch, DEALS, Q).is_deal
    assert not evaluate(make("Honda Civic Type R", 5000), watch, DEALS, Q).is_deal
    assert not evaluate(make("Honda Civic for parts", 1500), watch, DEALS, Q).is_deal
    assert not evaluate(make("2015 Honda Civic", 5000, "Financing available, OMVIC dealer"), watch, DEALS, Q).is_deal
    assert not evaluate(make("Honda Accord", 5000), watch, DEALS, Q).is_deal
    assert not evaluate(make("Honda Civic", 123), watch, DEALS, Q).is_deal  # placeholder price
    assert not evaluate(make("Honda Civic", None), watch, DEALS, Q).is_deal
    assert not evaluate(make("Honda Civic", 9000), watch, DEALS, Q).is_deal
    # "iso" must not match inside other words
    assert evaluate(make("Honda Civic, isofix seats", 5000), watch, DEALS, Q).is_deal


def test_signals():
    watch = Watch(name="specials", queries=["car"], max_price=3000, match_query_terms=False)
    v = evaluate(make("2008 Corolla as is", 1800, "Check engine light, must go"), watch, DEALS, "car")
    assert v.is_deal
    assert {"as is", "check engine", "must go"} <= set(v.signals)


def test_search_max_price():
    assert search_max_price(Watch(name="a", queries=["x"]), DEALS) is None
    assert search_max_price(Watch(name="a", queries=["x"], max_price=5000), DEALS) == 5000
    assert search_max_price(Watch(name="a", queries=["x"], market_value=9000), DEALS) == (9000 - 500 - 1000) / 1.13
    by_year = Watch(name="a", queries=["x"], market_value_by_year={2012: 6000, 2016: 12000})
    assert search_max_price(by_year, DEALS) == (12000 - 500 - 1000) / 1.13
    assert search_max_price(Watch(name="a", queries=["x"], market_value="auto"), DEALS) is None
