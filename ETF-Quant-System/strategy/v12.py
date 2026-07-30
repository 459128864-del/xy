"""ETF multi-factor rotation model V1.2."""

from dataclasses import dataclass

import pandas as pd

from factors.atr import average_true_range
from factors.capital import capital_strength
from factors.drawdown import rolling_drawdown
from factors.market import market_environment
from factors.trend import trend_strength
from factors.volatility import annualized_volatility
from strategy.momentum import momentum_score


@dataclass(frozen=True)
class V12Config:
    trend_weight: float = 0.20
    momentum_weight: float = 0.25
    capital_weight: float = 0.20
    risk_weight: float = 0.15
    market_weight: float = 0.20
    buy_score: float = 80.0
    sell_score: float = 60.0
    top_n: int = 3
    ma_window: int = 60
    atr_window: int = 14
    atr_multiple: float = 2.0
    trailing_window: int = 20


def v12_signals(
    prices: pd.DataFrame,
    config: V12Config = V12Config(),
) -> pd.DataFrame:
    """Return factor scores and buy/sell signals for long-form OHLCV data."""
    required = {"date", "symbol", "high", "low", "close", "volume"}
    if missing := required.difference(prices.columns):
        raise ValueError(f"missing columns: {sorted(missing)}")

    frame = prices.copy().sort_values(["symbol", "date"]).reset_index(drop=True)
    parts: list[pd.DataFrame] = []
    for _, group in frame.groupby("symbol", sort=False):
        item = group.copy()
        close = item["close"]
        item["ma60"] = close.rolling(config.ma_window).mean()
        item["trend_raw"] = trend_strength(close, 20)
        item["momentum_raw"] = momentum_score(close, 20)
        item["capital_raw"] = capital_strength(close, item["volume"], 20)
        volatility = annualized_volatility(close, 20)
        drawdown = rolling_drawdown(close, 60).abs()
        item["risk_raw"] = -(0.6 * volatility + 0.4 * drawdown)
        item["market_score"] = market_environment(close, config.ma_window) * 100
        item["atr"] = average_true_range(
            item["high"], item["low"], close, config.atr_window
        )
        rolling_high = close.rolling(config.trailing_window, min_periods=1).max()
        item["atr_stop"] = rolling_high - config.atr_multiple * item["atr"]
        parts.append(item)

    frame = pd.concat(parts, ignore_index=True)
    raw_columns = ["trend_raw", "momentum_raw", "capital_raw", "risk_raw"]
    percentile = frame.groupby("date")[raw_columns].rank(pct=True) * 100
    for column in raw_columns:
        frame[column.removesuffix("_raw") + "_score"] = percentile[column]

    frame["score"] = (
        config.trend_weight * frame["trend_score"]
        + config.momentum_weight * frame["momentum_score"]
        + config.capital_weight * frame["capital_score"]
        + config.risk_weight * frame["risk_score"]
        + config.market_weight * frame["market_score"]
    )
    frame["rank"] = frame.groupby("date")["score"].rank(
        method="first", ascending=False
    )
    frame["buy"] = (
        frame["score"].gt(config.buy_score)
        & frame["rank"].le(config.top_n)
        & frame["close"].gt(frame["ma60"])
    )
    frame["sell_score"] = frame["score"].lt(config.sell_score)
    frame["sell_ma60"] = frame["close"].lt(frame["ma60"])
    frame["sell_atr"] = frame["close"].lt(frame["atr_stop"])
    frame["sell"] = frame[["sell_score", "sell_ma60", "sell_atr"]].any(axis=1)
    frame["sell_reason"] = frame.apply(_sell_reason, axis=1)

    output = [
        "date",
        "symbol",
        "close",
        "ma60",
        "trend_score",
        "momentum_score",
        "capital_score",
        "risk_score",
        "market_score",
        "score",
        "rank",
        "atr",
        "atr_stop",
        "buy",
        "sell",
        "sell_reason",
    ]
    return frame[output]


def _sell_reason(row: pd.Series) -> str:
    reasons = []
    if row["sell_score"]:
        reasons.append("评分低于60")
    if row["sell_ma60"]:
        reasons.append("跌破MA60")
    if row["sell_atr"]:
        reasons.append("ATR止损")
    return "、".join(reasons)
