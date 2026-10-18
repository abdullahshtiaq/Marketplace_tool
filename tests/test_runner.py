import os
from pathlib import Path

import pytest
import yaml

from flipwatch.config import Config, ConfigError, DealSettings, Watch, parse_config
from flipwatch.models import Listing
from flipwatch.runner import Runner
from flipwatch.store import Store


class FakeSource:
    name = "kijiji"

    def __init__(self):
        self.results = []
        self.calls = []

    def search(self, query, filters):
        self.calls.append((query, filters))
        return list(self.results)

    def close(self):
        pass


class FakeNotifier:
    def __init__(self):
        self.sent = []

    def send(self, title, body, listing=None):
        self.sent.append((title, body, listing))


def car(id_, title, price):
    return Listing("kijiji", id_, title, price, f"https://www.kijiji.ca/v-x/{id_}")


DEALS = DealSettings(fixed_costs=500, purchase_tax_pct=0.0, min_profit=1000, min_roi=0.15,
                     auto_min_comps=3, auto_resale_pct=1.0)


def make_runner(tmp_path, watch):
    cfg = Config(watches=[watch], deals=DEALS, request_delay_seconds=0)
    source, notifier = FakeSource(), FakeNotifier()
    runner = Runner(cfg, Store(tmp_path / "t.db"), {"kijiji": source}, [notifier], sleep=lambda s: None)
    return runner, source, notifier


@pytest.fixture
def fixed(tmp_path):
    return make_runner(tmp_path, Watch(name="civic", queries=["civic"], sources=["kijiji"],
                                       market_value=9000, min_year=2012, max_km=200000))


def test_first_run_primes_then_alerts_on_new(fixed):
    runner, source, notifier = fixed
    source.results = [car("1", "2014 Civic", 5000)]
    assert runner.run_cycle() == 0  # existing listings are recorded silently
    source.results.append(car("2", "2015 Civic 140k km", 6000))
    source.results.append(car("3", "2015 Civic", 8500))  # not a deal
    assert runner.run_cycle() == 1
    title, body, listing = notifier.sent[0]
    assert listing.id == "2"
    assert "2015 | 140,000 km" in body and "Resale est. $9,000" in body
    assert runner.run_cycle() == 0  # no repeats
    query, filters = source.calls[0]
    assert query == "civic" and filters.max_price == 9000 - 500 - 1000 and filters.min_year == 2012


def test_price_drop_realerts(fixed):
    runner, source, notifier = fixed
    runner.run_cycle()
    source.results = [car("5", "2014 Civic", 8000)]
    assert runner.run_cycle() == 0
    source.results = [car("5", "2014 Civic", 6000)]
    assert runner.run_cycle() == 1
    assert notifier.sent[-1][0].startswith("PRICE DROP")
    assert "Was $8,000" in notifier.sent[-1][1]


def test_auto_value_from_comps(tmp_path):
    runner, source, notifier = make_runner(
        tmp_path, Watch(name="corolla", queries=["corolla"], sources=["kijiji"], market_value="auto")
    )
    source.results = [
        car("1", "2014 Corolla", 9000),
        car("2", "2015 Corolla", 10000),
        car("3", "2013 Corolla", 11000),
        car("4", "2020 Corolla", 25000),  # outside the +/-1 year window
        car("5", "2014 Corolla for parts", 1000),  # excluded, not a comp
    ]
    runner.run_cycle()  # priming builds comps
    assert source.calls[0][1].max_price is None  # auto needs the full price range

    source.results = [car("6", "2014 Corolla", 7500)]
    assert runner.run_cycle() == 1  # median 10000 - 500 costs - 7500 = 2000 profit
    assert "median ask, 3 2013-2015 comps" in notifier.sent[0][1]

    source.results = [car("7", "2018 Corolla", 5000)]  # no comps near 2018 yet
    assert runner.run_cycle() == 0


def test_source_errors_do_not_stop_cycle(fixed):
    runner, source, _ = fixed

    def boom(*a, **k):
        raise ValueError("parser broke")

    source.search = boom
    assert runner.run_cycle() == 0


def test_parse_config_example():
    raw = yaml.safe_load((Path(__file__).parent.parent / "config.example.yaml").read_text())
    cfg = parse_config(raw)
    assert cfg.watches and cfg.kijiji.category_id == 174 and cfg.kijiji.location_slug == "calgary"
    assert cfg.watches[0].auto_value
    assert cfg.watches[-1].queries == [""]
    assert cfg.notify.ntfy_topic in (None, os.environ.get("NTFY_TOPIC"))


def test_parse_config_rejects_typos():
    with pytest.raises(ConfigError, match="max_prise"):
        parse_config({"watches": [{"name": "a", "queries": ["x"], "max_prise": 5}]})
    with pytest.raises(ConfigError, match="number or 'auto'"):
        parse_config({"watches": [{"name": "a", "queries": ["x"], "market_value": "lots"}]})
