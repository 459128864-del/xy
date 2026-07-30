"""Drawdown factors."""

import pandas as pd


def rolling_drawdown(close: pd.Series, window: int = 60) -> pd.Series:
    """Return drawdown from the rolling high (zero is best)."""
    return close.div(close.rolling(window, min_periods=1).max()).sub(1)
