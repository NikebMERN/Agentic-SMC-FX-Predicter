# engine/risk_calc.py
"""Automated pip / position-size calculator.

Given a level set (entry, stop loss, take profit) and the trader's
account (balance + risk percent), computes:
  - pip distances to SL and TP
  - pip value per standard lot in USD (cross pairs converted through the
    cached USD rate of the quote currency; flagged approximate if no
    conversion rate is available)
  - the lot size that risks exactly balance * risk_pct
  - money at risk, potential reward, risk:reward ratio
"""
from utils.logger import get_logger

log = get_logger("engine.risk_calc")

STANDARD_LOT = 100_000
MIN_LOT = 0.01
MAX_LOT = 100.0


def pip_size_for(symbol: str) -> float:
    return 0.01 if symbol.upper().endswith("JPY") else 0.0001


def _quote_usd_rate(quote: str) -> tuple[float | None, bool]:
    """USD value of 1 unit of the quote currency, from cached data.

    Returns (rate, approximate). approximate=True when no conversion
    pair could be found and the caller should flag the numbers.
    """
    quote = quote.upper()
    if quote == "USD":
        return 1.0, False
    from engine.data import get_latest_price
    direct = get_latest_price(f"{quote}USD")     # e.g. GBPUSD for GBP
    if direct:
        return float(direct), False
    inverse = get_latest_price(f"USD{quote}")    # e.g. USDJPY for JPY
    if inverse:
        return 1.0 / float(inverse), False
    return None, True


def pip_calculator(
    symbol: str,
    entry: float,
    stop_loss: float,
    take_profit: float,
    balance: float = 1000.0,
    risk_pct: float = 1.0,
    risk_amount: float | None = None,
) -> dict:
    """Full position math for one trade idea. Pure numbers in, dict out.

    The position NEVER risks more than the user asked for: the lot size
    is floored (not rounded) so actual risk <= requested risk. The only
    exception is the broker minimum of 0.01 lots — when even that risks
    more than requested, the result carries risk_exceeds_requested=True
    and a warning instead of silently over-risking.

    risk_amount (a fixed dollar amount) overrides balance * risk_pct
    when provided.
    """
    import math

    symbol = symbol.upper()
    entry = float(entry)
    stop_loss = float(stop_loss)
    take_profit = float(take_profit)
    balance = max(0.0, float(balance))
    risk_pct = min(max(float(risk_pct), 0.01), 10.0)  # sane bounds

    pip = pip_size_for(symbol)
    sl_pips = abs(entry - stop_loss) / pip
    tp_pips = abs(take_profit - entry) / pip
    if sl_pips <= 0:
        raise ValueError("Stop loss must differ from entry")

    # Pip value of one standard lot, expressed in the QUOTE currency,
    # then converted to USD.
    pip_value_quote = pip * STANDARD_LOT  # e.g. 10 USD on EURUSD, 1000 JPY on USDJPY
    rate, approximate = _quote_usd_rate(symbol[3:])
    pip_value_usd = pip_value_quote * (rate if rate else (1.0 / entry if symbol.startswith("USD") else 1.0))

    if risk_amount is not None and float(risk_amount) > 0:
        requested_risk = float(risk_amount)
    else:
        requested_risk = balance * risk_pct / 100.0

    exact_lot = requested_risk / (sl_pips * pip_value_usd) if pip_value_usd > 0 else MIN_LOT
    # floor to the broker step so actual risk never exceeds the request
    # (epsilon guards against float noise turning 0.05 into 0.04)
    lot_size = math.floor(exact_lot * 100 + 1e-9) / 100
    risk_exceeds_requested = False
    warning = None
    if lot_size < MIN_LOT:
        lot_size = MIN_LOT
        min_risk = MIN_LOT * sl_pips * pip_value_usd
        if min_risk > requested_risk + 0.005:
            risk_exceeds_requested = True
            warning = (
                f"The broker minimum of {MIN_LOT} lots risks "
                f"${min_risk:.2f} — more than your requested ${requested_risk:.2f}."
            )
    lot_size = min(lot_size, MAX_LOT)

    actual_risk = round(lot_size * sl_pips * pip_value_usd, 2)
    reward_amount = round(lot_size * tp_pips * pip_value_usd, 2)

    return {
        "symbol": symbol,
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "balance": round(balance, 2),
        "risk_pct": risk_pct,
        "requested_risk_amount": round(requested_risk, 2),
        "pip_size": pip,
        "sl_pips": round(sl_pips, 1),
        "tp_pips": round(tp_pips, 1),
        "pip_value_per_lot_usd": round(pip_value_usd, 2),
        "lot_size": round(lot_size, 2),
        "risk_amount": actual_risk,
        "reward_amount": reward_amount,
        "risk_reward": round(tp_pips / sl_pips, 2),
        "approximate": approximate,
        "risk_exceeds_requested": risk_exceeds_requested,
        "warning": warning,
    }
