"""Stateful ETF rotation backtest with portfolio drawdown control."""

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RotationBacktestConfig:
    top_n: int = 3
    rebalance_every: int = 5
    transaction_cost: float = 0.0005
    initial_capital: float = 1_000_000.0
    max_drawdown_limit: Optional[float] = None
    cooldown_days: int = 10


@dataclass(frozen=True)
class RotationBacktestResult:
    equity: pd.Series
    weights: pd.DataFrame
    returns: pd.Series
    metrics: dict[str, float]


def run_rotation_backtest(
    prices: pd.DataFrame,
    signals: pd.DataFrame,
    config: RotationBacktestConfig = RotationBacktestConfig(),
) -> RotationBacktestResult:
    """Run a next-day, equal-weight rotation backtest without look-ahead."""
    if config.top_n < 1 or config.rebalance_every < 1:
        raise ValueError("top_n and rebalance_every must be positive")
    if config.max_drawdown_limit is not None and not 0 < config.max_drawdown_limit < 1:
        raise ValueError("max_drawdown_limit must be in (0, 1)")

    close = prices.pivot(index="date", columns="symbol", values="close").sort_index()
    score = signals.pivot(index="date", columns="symbol", values="score").reindex(
        index=close.index, columns=close.columns
    )
    daily_asset_returns = close.pct_change(fill_method=None).fillna(0.0)
    weights = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    strategy_returns = pd.Series(0.0, index=close.index, name="return")

    current_weights = pd.Series(0.0, index=close.columns)
    equity_value = config.initial_capital
    peak_value = equity_value
    cooldown = 0
    period_start_value = equity_value
    period_returns: list[float] = []

    for index, date in enumerate(close.index):
        gross_return = float((current_weights * daily_asset_returns.loc[date]).sum())
        equity_value *= 1 + gross_return
        peak_value = max(peak_value, equity_value)
        drawdown = equity_value / peak_value - 1
        target = current_weights.copy()

        risk_exit = (
            config.max_drawdown_limit is not None
            and drawdown <= -config.max_drawdown_limit
            and bool(current_weights.abs().sum())
        )
        is_rebalance = index % config.rebalance_every == 0

        if risk_exit:
            target[:] = 0.0
            cooldown = config.cooldown_days
            # Start a new risk budget after the forced exit. Otherwise the old
            # high-water mark would immediately trigger another exit on re-entry.
            peak_value = equity_value
        elif cooldown > 0:
            target[:] = 0.0
            cooldown -= 1
        elif is_rebalance:
            ranking = score.loc[date].dropna().nlargest(config.top_n).index
            target[:] = 0.0
            if len(ranking):
                target.loc[ranking] = 1.0 / len(ranking)

        turnover = float((target - current_weights).abs().sum())
        net_return = gross_return - turnover * config.transaction_cost
        if turnover:
            equity_value *= 1 - turnover * config.transaction_cost
        strategy_returns.loc[date] = net_return
        current_weights = target
        weights.loc[date] = current_weights

        if (is_rebalance or risk_exit) and index > 0:
            period_returns.append(equity_value / period_start_value - 1)
            period_start_value = equity_value

    equity = config.initial_capital * (1 + strategy_returns).cumprod()
    active = strategy_returns[strategy_returns.ne(0)]
    daily_std = strategy_returns.std()
    downside = strategy_returns[strategy_returns.lt(0)].std()
    metrics = {
        "total_return": float(equity.iloc[-1] / config.initial_capital - 1),
        "annualized_return": float(
            (equity.iloc[-1] / config.initial_capital) ** (252 / len(equity)) - 1
        ),
        "annualized_volatility": float(daily_std * np.sqrt(252)),
        "sharpe": float(strategy_returns.mean() / daily_std * np.sqrt(252))
        if daily_std
        else 0.0,
        "sortino": float(strategy_returns.mean() / downside * np.sqrt(252))
        if downside
        else 0.0,
        "max_drawdown": float((equity / equity.cummax() - 1).min()),
        "daily_win_rate": float(active.gt(0).mean()) if len(active) else 0.0,
        "rebalance_win_rate": float(np.mean(np.asarray(period_returns) > 0))
        if period_returns
        else 0.0,
        "average_turnover": float(weights.diff().abs().sum(axis=1).mean()),
    }
    return RotationBacktestResult(equity, weights, strategy_returns, metrics)
