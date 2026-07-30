"""Volatility factors."""

import numpy as np
import pandas as pd


def annualized_volatility(close: pd.Series, window: int = 20) -> pd.Series:
    """Return rolling annualized volatility using 252 trading days."""
    return close.pct_change().rolling(window).std().mul(np.sqrt(252))
