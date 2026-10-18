import pytest

from flipwatch.config import Config, DealSettings, Watch, parse_config
from flipwatch.models import Listing
from flipwatch.runner import Runner
from flipwatch.store import Store


class FakeSource:
    name = "kijiji"

    def __init__(self):
        self.results = []
        self.calls = []

    def search(self, query, max_price=None):
        self.calls.append((query, max_price))
        return list(self.results)

    def close(self):
        pass


class FakeNotifier:
    def __init__(self):
        self.sent = []

    def send(self, title, body, listing=None):
        self.sent.append((title, body, listing))


def listing(id_, title, price):
    return Listing("kijiji", id_, title, price, f"https://www.kijiji.ca/v-x/{id_}")


@pytest.fixture
def setup(tmp_path):
    cfg = Config(
        watches=[Watch(name="zard", queries=["charizard"], sources=["kijiji"], market_value=150)],
        deals=DealSettings(selling_fee_pct=0.1, fixed_costs=5, min_profit=30, min_roi=0.3),
        request_delay_seconds=0,
    )
    source, notifier = FakeSource(), FakeNotifier()
    runner = Runner(cfg, Store(tmp_path / "t.db"), {"kijiji": source}, [notifier], sleep=lambda s: None)
    return runner, source, notifier


def test_first_run_primes_then_alerts_on_new(setup):
    runner, source, notifier = setup
    source.results = [listing("1", "Charizard holo", 40)]
    assert runner.run_cycle() == 0  # existing listings are recorded silently
    source.results.append(listing("2", "Charizard 1st edition", 50))
    source.results.append(listing("3", "Charizard", 140))  # not a deal
    assert runner.run_cycle() == 1
    assert notifier.sent[0][2].id == "2"
    assert runner.run_cycle() == 0  # no repeats
    assert source.calls[0] == ("charizard", 150 * 0.9 - 5 - 30)


def test_price_drop_realerts(setup):
    runner, source, notifier = setup
    runner.run_cycle()
    source.results = [listing("5", "Charizard", 140)]
    assert runner.run_cycle() == 0
    source.results = [listing("5", "Charizard", 60)]
    assert runner.run_cycle() == 1
    assert notifier.sent[-1][0].startswith("PRICE DROP")
    assert "Was $140" in notifier.sent[-1][1]


def test_source_errors_do_not_stop_cycle(setup):
    runner, source, _ = setup

    def boom(*a, **k):
        raise ValueError("parser broke")

    source.search = boom
    assert runner.run_cycle() == 0


def test_parse_config_example():
    import yaml
    from pathlib import Path

    raw = yaml.safe_load((Path(__file__).parent.parent / "config.example.yaml").read_text())
    cfg = parse_config(raw)
    assert cfg.watches and cfg.kijiji.location_id == 1700272
    assert cfg.notify.ntfy_topic in (None, __import__("os").environ.get("NTFY_TOPIC"))


def test_parse_config_rejects_typos():
    from flipwatch.config import ConfigError

    with pytest.raises(ConfigError, match="max_prise"):
        parse_config({"watches": [{"name": "a", "queries": ["x"], "max_prise": 5}]})
