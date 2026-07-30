"""Trend-preserving ETF rotation with volatility and regime filters."""

from dataclasses import dataclass

import pandas as pd

from factors.trend import trend_strength
from factors.volatility import annualized_volatility


@dataclass(frozen=True)
class OptimizedRotationConfig:
    trend_window: int = 20
    ma_window: int = 60
    volatility_window: int = 20
    volatility_quantile: float = 0.70


def optimized_rotation_scores(
    prices: pd.DataFrame,
    config: OptimizedRotationConfig = OptimizedRotationConfig(),
) -> pd.DataFrame:
    """Keep trend ranking, but reject weak-trend and high-volatility ETFs."""
    required = {"date", "symbol", "close"}
    if missing := required.difference(prices.columns):
        raise ValueError(f"missing columns: {sorted(missing)}")
    if not 0 < config.volatility_quantile <= 1:
        raise ValueError("volatility_quantile must be in (0, 1]")

    frame = prices.copy().sort_values(["symbol", "date"]).reset_index(drop=True)
    grouped = frame.groupby("symbol", group_keys=False)["close"]
    frame["trend"] = grouped.transform(
        lambda close: trend_strength(close, config.trend_window)
    )
    frame["ma"] = grouped.transform(
        lambda close: close.rolling(config.ma_window).mean()
    )
    frame["volatility"] = grouped.transform(
        lambda close: annualized_volatility(close, config.volatility_window)
    )
    frame["volatility_limit"] = frame.groupby("date")["volatility"].transform(
        lambda values: values.quantile(config.volatility_quantile)
    )
    frame["volatility_pass"] = frame["volatility"].le(frame["volatility_limit"])
    frame["trend_pass"] = frame["close"].gt(frame["ma"])
    frame["eligible"] = frame["volatility_pass"] & frame["trend_pass"]
    frame["score"] = frame["trend"].where(frame["eligible"])
    return frame[
        [
            "date",
            "symbol",
            "score",
            "trend",
            "volatility",
            "volatility_limit",
            "volatility_pass",
            "trend_pass",
            "eligible",
        ]
    ]


def baseline_trend_scores(
    prices: pd.DataFrame,
    trend_window: int = 20,
) -> pd.DataFrame:
    """Unfiltered trend baseline used for an apples-to-apples comparison."""
    frame = prices.copy().sort_values(["symbol", "date"]).reset_index(drop=True)
    frame["score"] = frame.groupby("symbol", group_keys=False)["close"].transform(
        lambda close: trend_strength(close, trend_window)
    )
    frame["eligible"] = frame["score"].notna()
    return frame[["date", "symbol", "score", "eligible"]]
