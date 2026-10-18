from flipwatch.config import DealSettings, Watch
from flipwatch.evaluator import evaluate, search_max_price
from flipwatch.models import Listing


def make(title, price, description=""):
    return Listing("kijiji", "1", title, price, "https://example.com/v-1", description=description)


DEALS = DealSettings(selling_fee_pct=0.10, fixed_costs=5, min_profit=30, min_roi=0.3, min_price=5)


def test_flip_margin():
    watch = Watch(name="zard", queries=["charizard"], market_value=150)
    v = evaluate(make("Charizard holo base set", 60), watch, DEALS, "charizard")
    assert v.is_deal
    assert v.est_profit == 150 * 0.9 - 5 - 60
    assert not evaluate(make("Charizard holo", 110), watch, DEALS, "charizard").is_deal


def test_roi_threshold():
    watch = Watch(name="gpu", queries=["rtx 3080"], market_value=1000, min_profit=10)
    # profit 895 - 800 = 95, ROI 12%
    v = evaluate(make("RTX 3080", 800), watch, DEALS, "rtx 3080")
    assert not v.is_deal and "ROI" in v.reason


def test_filters():
    watch = Watch(name="zard", queries=["charizard"], max_price=100, exclude=["plush"])
    q = "charizard"
    assert not evaluate(make("WTB Charizard", 20), watch, DEALS, q).is_deal
    assert not evaluate(make("Charizard plush", 20), watch, DEALS, q).is_deal
    assert not evaluate(make("Pikachu card", 20), watch, DEALS, q).is_deal
    assert not evaluate(make("Charizard", 1), watch, DEALS, q).is_deal  # placeholder price
    assert not evaluate(make("Charizard", None), watch, DEALS, q).is_deal
    assert not evaluate(make("Charizard", 150), watch, DEALS, q).is_deal
    assert evaluate(make("Charizard", 50), watch, DEALS, q).is_deal
    # "iso" must not match inside other words
    assert evaluate(make("Charizard isolated holo", 50), watch, DEALS, q).is_deal


def test_accents_and_signals():
    watch = Watch(name="bulk", queries=["pokemon cards"], max_price=60, require_any=["binder", "lot"])
    v = evaluate(make("Pokémon cards binder", 40, "moving, must go"), watch, DEALS, "pokemon cards")
    assert v.is_deal
    assert {"binder", "moving", "must go"} <= set(v.signals)
    assert not evaluate(make("Pokémon cards single", 40), watch, DEALS, "pokemon cards").is_deal


def test_search_max_price():
    assert search_max_price(Watch(name="a", queries=["x"]), DEALS) is None
    assert search_max_price(Watch(name="a", queries=["x"], max_price=50), DEALS) == 50
    assert search_max_price(Watch(name="a", queries=["x"], market_value=150), DEALS) == 150 * 0.9 - 5 - 30
    assert search_max_price(Watch(name="a", queries=["x"], market_value=150, max_price=40), DEALS) == 40
