# services/risk.py

def calculate_lot_size(account_balance, risk_percent, stop_loss_pips, pip_value=10):
    """
    Basic lot size calculator.
    - account_balance: total balance of account
    - risk_percent: percentage of account to risk
    - stop_loss_pips: distance to SL
    - pip_value: pip value (default $10 per lot for major pairs)

    Returns: lot size
    """
    risk_amount = account_balance * (risk_percent / 100)
    lot_size = risk_amount / (stop_loss_pips * pip_value)
    return round(lot_size, 2)
