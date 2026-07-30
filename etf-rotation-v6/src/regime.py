"""Market regime classification from trend and cross-sectional breadth."""

from __future__ import annotations

import pandas as pd


def classify_regime(
    prices: pd.DataFrame, trend_window: int, breadth_threshold: float
) -> pd.DataFrame:
    pivot = prices.pivot(index="date", columns="symbol", values="close").sort_index()
    moving_average = pivot.rolling(trend_window, min_periods=trend_window).mean()
    breadth = pivot.gt(moving_average).mean(axis=1)
    market = pivot.mean(axis=1)
    market_trend = market.gt(market.rolling(trend_window).mean())
    regime = pd.Series("defense", index=pivot.index)
    regime.loc[market_trend] = "balanced"
    regime.loc[market_trend & breadth.ge(breadth_threshold)] = "attack"
    return (
        pd.DataFrame({"breadth": breadth, "regime": regime})
        .rename_axis("date")
        .reset_index()
    )
