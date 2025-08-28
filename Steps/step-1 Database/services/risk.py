
from __future__ import annotations

def pip_value_per_lot(symbol: str, price: float) -> float:
    """Return approximate USD value of 1 pip per 1.0 lot.
    - For XXXUSD (quote USD, non-JPY): ~ $10 per lot per pip.
    - For JPY quotes: pip size is 0.01, so USD value ~= 100000 * 0.01 / price
    - For others (crosses), default to 10 (can be refined using conversion).
    """
    sym = symbol.upper()
    if sym.endswith("USD") and not sym.endswith("JPYUSD"):
        # e.g., EURUSD, GBPUSD, AUDUSD
        return 10.0
    if sym.endswith("JPY"):
        # e.g., USDJPY, EURJPY; pip size is 0.01 of quote currency
        # Convert quote to USD assuming USD is the base for value
        if price and price > 0:
            return 100000 * 0.01 / price  # ~= 1000 / price
        return 0.0
    # Fallback: treat as $10 per pip per lot (rough approximation)
    return 10.0

def calc_lot_size(
    account_balance: float,
    risk_per_trade: float,
    stop_loss_pips: float,
    symbol: str,
    current_price: float,
    min_lot: float = 0.01,
    lot_step: float = 0.01,
    max_lot: float | None = None
) -> float:
    """Risk-based lot size.
    lot = (balance * risk%) / (stop_pips * pip_value_per_lot)
    Rounded down to lot_step and clamped between min_lot and max_lot.
    """
    if stop_loss_pips <= 0 or current_price <= 0 or account_balance <= 0 or risk_per_trade <= 0:
        return min_lot

    risk_amount = account_balance * risk_per_trade
    pip_val = pip_value_per_lot(symbol, current_price)
    if pip_val <= 0:
        return min_lot

    raw_lots = risk_amount / (stop_loss_pips * pip_val)

    # round down to nearest step
    steps = int(raw_lots / lot_step)
    lots = steps * lot_step
    if lots < min_lot:
        lots = min_lot
    if max_lot is not None and lots > max_lot:
        lots = max_lot
    # round to 2 decimals for typical FX brokers
    return round(lots, 2)
