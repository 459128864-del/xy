"""Market-regime factors."""

import pandas as pd


def market_environment(close: pd.Series, ma_window: int = 60) -> pd.Series:
    """Score a bullish environment from MA position and MA slope."""
    ma = close.rolling(ma_window).mean()
    above_ma = close.gt(ma).astype(float)
    rising_ma = ma.gt(ma.shift(5)).astype(float)
    return 0.5 * above_ma + 0.5 * rising_ma
