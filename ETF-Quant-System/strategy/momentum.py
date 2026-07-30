"""Momentum scoring model."""

import pandas as pd


def momentum_score(close: pd.Series, lookback: int = 20) -> pd.Series:
    """Return lookback total return as a momentum score."""
    if lookback < 1:
        raise ValueError("lookback must be positive")
    return close.pct_change(lookback)
