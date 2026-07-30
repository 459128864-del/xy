"""Multi-factor ETF rotation model."""

import pandas as pd

from factors.drawdown import rolling_drawdown
from factors.trend import trend_strength
from factors.volatility import annualized_volatility
from strategy.momentum import momentum_score


def rotation_scores(
    prices: pd.DataFrame,
    momentum_lookback: int = 20,
    risk_window: int = 20,
) -> pd.DataFrame:
    """Calculate cross-sectional ETF scores for long-form price data."""
    required = {"date", "symbol", "close"}
    if missing := required.difference(prices.columns):
        raise ValueError(f"missing columns: {sorted(missing)}")

    frame = prices.copy().sort_values(["symbol", "date"])
    grouped = frame.groupby("symbol", group_keys=False)["close"]
    frame["momentum"] = grouped.transform(
        lambda values: momentum_score(values, momentum_lookback)
    )
    frame["trend"] = grouped.transform(lambda values: trend_strength(values, risk_window))
    frame["volatility"] = grouped.transform(
        lambda values: annualized_volatility(values, risk_window)
    )
    frame["drawdown"] = grouped.transform(
        lambda values: rolling_drawdown(values, risk_window)
    )

    factors = ["momentum", "trend", "volatility", "drawdown"]
    ranks = frame.groupby("date")[factors].rank(pct=True)
    frame["score"] = (
        0.4 * ranks["momentum"]
        + 0.3 * ranks["trend"]
        - 0.2 * ranks["volatility"]
        + 0.1 * ranks["drawdown"]
    )
    return frame[["date", "symbol", "score"]]
