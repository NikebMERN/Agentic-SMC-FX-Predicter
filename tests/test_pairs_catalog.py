# tests/test_pairs_catalog.py
from utils.pairs import DEFAULT_FX_PAIRS, merge_pairs


def test_default_catalog_has_many_pairs():
    assert len(DEFAULT_FX_PAIRS) == 96
    assert "EURUSD" in DEFAULT_FX_PAIRS
    assert "GBPJPY" in DEFAULT_FX_PAIRS
    assert "USDSGD" in DEFAULT_FX_PAIRS
    assert "MXNJPY" in DEFAULT_FX_PAIRS
    assert "USDINR" in DEFAULT_FX_PAIRS


def test_pairs_from_env_accepts_slashes():
    from utils.pairs import pairs_from_env

    assert pairs_from_env("EUR/USD, GBP/USD") == ["EURUSD", "GBPUSD"]


def test_config_uses_full_catalog_when_env_unset(monkeypatch):
    monkeypatch.setenv("SUPPORTED_PAIRS", "")
    import importlib
    import utils.config as cfg

    importlib.reload(cfg)
    assert len(cfg.SUPPORTED_PAIRS) == 96


def test_merge_pairs_deduplicates():
    merged = merge_pairs(["EURUSD", "GBPUSD"], ["EURUSD", "USDJPY"])
    assert merged == ["EURUSD", "GBPUSD", "USDJPY"]
