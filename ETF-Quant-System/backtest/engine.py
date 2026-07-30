"""Simple cross-sectional ETF rotation backtest."""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BacktestConfig:
    top_n: int = 3
    rebalance_every: int = 5
    transaction_cost: float = 0.0005
    initial_capital: float = 1_000_000.0


@dataclass(frozen=True)
class BacktestResult:
    equity: pd.Series
    weights: pd.DataFrame
    metrics: dict[str, float]


def run_backtest(
    prices: pd.DataFrame,
    scores: pd.DataFrame,
    config: BacktestConfig = BacktestConfig(),
) -> BacktestResult:
    """Backtest lagged, equal-weight selections from long-form inputs."""
    if config.top_n < 1 or config.rebalance_every < 1:
        raise ValueError("top_n and rebalance_every must be positive")

    close = prices.pivot(index="date", columns="symbol", values="close").sort_index()
    score = scores.pivot(index="date", columns="symbol", values="score").reindex(close.index)
    returns = close.pct_change(fill_method=None).fillna(0.0)
    weights = pd.DataFrame(0.0, index=close.index, columns=close.columns)

    for index in range(0, len(close), config.rebalance_every):
        ranking = score.iloc[index].dropna().nlargest(config.top_n).index
        if len(ranking):
            weights.loc[close.index[index], ranking] = 1.0 / len(ranking)

    weights = weights.replace(0.0, np.nan).ffill().fillna(0.0)
    held_weights = weights.shift(1).fillna(0.0)
    turnover = weights.diff().abs().sum(axis=1)
    strategy_returns = (held_weights * returns).sum(axis=1)
    strategy_returns -= turnover * config.transaction_cost
    equity = config.initial_capital * (1 + strategy_returns).cumprod()

    daily_std = strategy_returns.std()
    metrics = {
        "total_return": float(equity.iloc[-1] / config.initial_capital - 1),
        "annualized_return": float(
            (equity.iloc[-1] / config.initial_capital) ** (252 / max(len(equity), 1)) - 1
        ),
        "annualized_volatility": float(daily_std * np.sqrt(252)),
        "sharpe": float(strategy_returns.mean() / daily_std * np.sqrt(252))
        if daily_std
        else 0.0,
        "max_drawdown": float((equity / equity.cummax() - 1).min()),
    }
    return BacktestResult(equity=equity, weights=weights, metrics=metrics)
