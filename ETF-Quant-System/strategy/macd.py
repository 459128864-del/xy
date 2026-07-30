"""MACD scoring model."""

import pandas as pd


def macd_score(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.Series:
    """Return the normalized MACD histogram."""
    if not 0 < fast < slow or signal < 1:
        raise ValueError("require 0 < fast < slow and signal > 0")
    fast_ema = close.ewm(span=fast, adjust=False).mean()
    slow_ema = close.ewm(span=slow, adjust=False).mean()
    macd = fast_ema - slow_ema
    histogram = macd - macd.ewm(span=signal, adjust=False).mean()
    return histogram.div(close.replace(0, pd.NA))
