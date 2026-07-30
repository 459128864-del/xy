"""Capital-flow proxies derived from price and volume."""

import pandas as pd


def capital_strength(
    close: pd.Series,
    volume: pd.Series,
    window: int = 20,
) -> pd.Series:
    """Measure volume-confirmed price strength without future data."""
    amount = close * volume
    amount_ratio = amount.div(amount.rolling(window).mean())
    signed_return = close.pct_change().clip(-0.1, 0.1)
    return signed_return.rolling(window).sum() * amount_ratio
