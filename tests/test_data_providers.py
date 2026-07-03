# tests/test_data_providers.py
"""OANDA provider: candle parsing, timezone normalisation, provider chain."""
import pandas as pd
import pytest

from engine import data as market_data

OANDA_CANDLES = [
    {
        "time": "2025-07-01T12:00:00.000000000Z",
        "complete": True,
        "volume": 123,
        "mid": {"o": "1.0800", "h": "1.0820", "l": "1.0790", "c": "1.0815"},
    },
    {
        "time": "2025-07-01T13:00:00.000000000Z",
        "complete": True,
        "volume": 98,
        "mid": {"o": "1.0815", "h": "1.0830", "l": "1.0805", "c": "1.0828"},
    },
    {   # still forming — must be dropped (no real close yet)
        "time": "2025-07-01T14:00:00.000000000Z",
        "complete": False,
        "volume": 10,
        "mid": {"o": "1.0828", "h": "1.0830", "l": "1.0825", "c": "1.0829"},
    },
]


def test_oanda_frame_parsing_drops_forming_candle_and_converts_timezone():
    df = market_data._frame_from_oanda(OANDA_CANDLES)
    assert len(df) == 2
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert df["Close"].iloc[0] == pytest.approx(1.0815)
    assert df["Volume"].iloc[1] == pytest.approx(98)
    # 12:00 UTC on 2025-07-01 is 08:00 in New York (EDT), stored tz-naive
    assert df.index[0] == pd.Timestamp("2025-07-01 08:00:00")
    assert df.index.tz is None
    assert df.index.name == "Timestamp"


def test_oanda_frame_empty_input():
    df = market_data._frame_from_oanda([])
    assert df.empty
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]


def test_oanda_granularity_mapping():
    assert market_data.OANDA_GRANULARITY["60min"] == "H1"
    assert market_data.OANDA_GRANULARITY["5min"] == "M5"
    with pytest.raises(LookupError, match="granularity"):
        market_data._fetch_oanda("EURUSD", "42min")


def test_provider_chain_prefers_oanda(monkeypatch):
    monkeypatch.setattr(market_data, "OANDA_API_KEY", "token")
    monkeypatch.setattr(market_data, "ALPHA_VANTAGE_API_KEY", "key")
    monkeypatch.setattr(market_data, "DATA_PROVIDER", "auto")
    labels = [label for label, _ in market_data._provider_chain()]
    assert labels[0] == "oanda"
    assert "alphavantage" in labels
    assert market_data.active_provider() == "oanda"


def test_provider_chain_falls_back_and_pins(monkeypatch):
    monkeypatch.setattr(market_data, "ALPHA_VANTAGE_API_KEY", "key")
    monkeypatch.setattr(market_data, "DATA_PROVIDER", "auto")

    monkeypatch.setattr(market_data, "OANDA_API_KEY", None)
    assert [l for l, _ in market_data._provider_chain()] == ["alphavantage", "alphavantage"]

    # pinned to oanda but no token -> empty chain, cache-only
    monkeypatch.setattr(market_data, "DATA_PROVIDER", "oanda")
    assert market_data._provider_chain() == []
    assert market_data.active_provider() == "none"

    # pinned to alphavantage ignores an available oanda token
    monkeypatch.setattr(market_data, "OANDA_API_KEY", "token")
    monkeypatch.setattr(market_data, "DATA_PROVIDER", "alphavantage")
    assert [l for l, _ in market_data._provider_chain()] == ["alphavantage", "alphavantage"]


def test_get_data_uses_cache_when_no_provider(synthetic_csv):
    df, source = market_data.get_data("TSTUSD", fetch=True)
    assert source == "cache"
    assert len(df) > 0
