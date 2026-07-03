# tests/test_strategy_mode.py
from unittest.mock import patch

import pytest

import app as app_module
from engine.confluence import _collect_votes, decide, normalize_strategy_mode
from tests.helpers import auth, register_and_login


def _minimal_analysis():
    """Synthetic analysis dict with one SMC and one ICT vote in play."""
    return {
        "symbol": "EURUSD",
        "bars": 100,
        "price": 1.1000,
        "atr": 0.0010,
        "structure": {
            "events": [{
                "pos": 95,
                "kind": "BOS",
                "direction": "bullish",
                "displacement": True,
                "level": 1.0990,
            }],
        },
        "valid_order_blocks": [],
        "fvgs": [],
        "sweeps": [{
            "side": "sellside",
            "bias": "bullish",
            "level": 1.0985,
            "bars_ago": 3,
        }],
        "premium_discount": {"zone": "discount", "position": 0.35},
        "ote": {"direction": "bullish", "low": 1.0950, "high": 1.0960},
        "breakers": [],
        "killzone": None,
        "swings": __import__("pandas").DataFrame(),
        "pools": [],
    }


def test_normalize_strategy_mode():
    assert normalize_strategy_mode(None) == "both"
    assert normalize_strategy_mode("SMC") == "smc"
    assert normalize_strategy_mode("ict-only") == "ict"
    assert normalize_strategy_mode("joint") == "both"
    with pytest.raises(ValueError, match="strategy must be"):
        normalize_strategy_mode("ml_only")


def test_collect_votes_respects_strategy_mode():
    analysis = _minimal_analysis()
    both = _collect_votes(analysis, "both")
    smc = _collect_votes(analysis, "smc")
    ict = _collect_votes(analysis, "ict")

    assert len(both) == len(smc) + len(ict)
    # votes are (direction, weight, reason, component) 4-tuples
    assert all("SMC" in r for _, _, r, _ in smc)
    assert all("ICT" in r for _, _, r, _ in ict)
    assert not any("ICT" in r for _, _, r, _ in smc)
    assert not any("SMC" in r for _, _, r, _ in ict)


def test_decide_includes_strategy_field():
    decision = decide(_minimal_analysis(), strategy_mode="smc")
    assert decision["strategy"] == "smc"


def test_analyze_passes_strategy_to_pipeline(client, admin_token):
    user = register_and_login(
        client,
        admin_token,
        username="strategyuser",
        email="strategy@test.local",
        password="SecurePass123!",
    )
    fake = {
        "symbol": "EURUSD",
        "interval": "60min",
        "strategy": "ict",
        "decision": {"action": "NO_TRADE", "confidence": 0.0, "entry": None},
        "feature_snapshot": {},
    }
    with patch.object(app_module, "predict_symbol", return_value=fake) as mock_predict:
        res = client.post(
            "/analyze",
            headers=auth(user["token"]),
            json={"symbol": "EURUSD", "interval": "60min", "fetch": False, "strategy": "ict"},
        )
    assert res.status_code == 200
    mock_predict.assert_called_once()
    assert mock_predict.call_args.kwargs["strategy_mode"] == "ict"


def test_analyze_rejects_invalid_strategy(client, admin_token):
    user = register_and_login(
        client,
        admin_token,
        username="badstrategy",
        email="badstrategy@test.local",
        password="SecurePass123!",
    )
    res = client.post(
        "/analyze",
        headers=auth(user["token"]),
        json={"symbol": "EURUSD", "strategy": "random"},
    )
    assert res.status_code == 400
    assert "strategy" in res.get_json()["error"]
