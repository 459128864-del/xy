"""Pure factor calculations using only current and past observations."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _efficiency(close: pd.Series, window: int) -> pd.Series:
    displacement = close.diff(window).abs()
    path = close.diff().abs().rolling(window).sum()
    return displacement.div(path.replace(0, np.nan)).fillna(0.0)


def _rolling_drawdown(close: pd.Series, window: int) -> pd.Series:
    peak = close.rolling(window, min_periods=window).max()
    return close.div(peak).sub(1.0)


def calculate_factors(
    prices: pd.DataFrame,
    *,
    momentum_windows: list[int],
    momentum_weights: list[float],
    skip_recent: int,
    efficiency_window: int,
    volatility_window: int,
    drawdown_window: int,
) -> pd.DataFrame:
    """Return point-in-time factors for long-form close-price data."""
    required = {"date", "symbol", "close"}
    missing = required.difference(prices.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    if len(momentum_windows) != len(momentum_weights):
        raise ValueError("momentum windows and weights must have equal length")

    frame = prices.loc[:, ["date", "symbol", "close"]].copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.sort_values(["symbol", "date"]).reset_index(drop=True)

    def per_symbol(group: pd.DataFrame) -> pd.DataFrame:
        close = group["close"].astype(float)
        anchor = close.shift(skip_recent)
        momentum = sum(
            weight * anchor.pct_change(window, fill_method=None)
            for window, weight in zip(momentum_windows, momentum_weights)
        )
        returns = close.pct_change(fill_method=None)
        result = group.copy()
        result["symbol"] = group.name
        result["momentum"] = momentum
        result["efficiency"] = _efficiency(close, efficiency_window)
        result["volatility"] = returns.rolling(volatility_window).std(ddof=0)
        result["drawdown"] = _rolling_drawdown(close, drawdown_window)
        return result

    return (
        frame.groupby("symbol", group_keys=False)
        .apply(per_symbol, include_groups=False)
        .reset_index(drop=True)
    )
