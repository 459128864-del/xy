"""Trend factors."""

import pandas as pd


def trend_strength(close: pd.Series, window: int = 20) -> pd.Series:
    """Return price distance from its moving average."""
    average = close.rolling(window).mean()
    return close.div(average).sub(1)
