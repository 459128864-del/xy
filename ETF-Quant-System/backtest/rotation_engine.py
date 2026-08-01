"""Stateful ETF rotation backtest with explicit T+1 close execution."""

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from backtest.engine import drift_weights, validate_execution


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
    """Signal at T close, execute at T+1 close, then affect T+1→T+2."""
    if config.top_n < 1 or config.rebalance_every < 1:
        raise ValueError("top_n and rebalance_every must be positive")
    if config.max_drawdown_limit is not None and not 0 < config.max_drawdown_limit < 1:
        raise ValueError("max_drawdown_limit must be in (0, 1)")
    close = prices.pivot(index="date", columns="symbol", values="close").sort_index()
    score = signals.pivot(index="date", columns="symbol", values="score").reindex(
        index=close.index, columns=close.columns
    )
    asset_returns = close.ffill().pct_change(fill_method=None)
    weights = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    strategy_returns = pd.Series(0.0, index=close.index, name="return")
    turnovers = pd.Series(0.0, index=close.index, name="turnover")
    current = pd.Series(0.0, index=close.columns)
    pending_target: pd.Series | None = None
    equity_value = config.initial_capital
    peak_value = equity_value
    cooldown_left = 0
    period_start_value = equity_value
    period_returns: list[float] = []

    for index, date in enumerate(close.index):
        interval_returns = asset_returns.loc[date]
        gross_return = float((current * interval_returns.fillna(0.0)).sum())
        pre_trade = drift_weights(current, interval_returns)
        target = pending_target if pending_target is not None else pre_trade
        weight_changes = target - pre_trade
        if pending_target is not None:
            validate_execution(weight_changes, close.loc[date])
        traded = float(weight_changes.abs().sum()) if pending_target is not None else 0.0
        cost_rate = traded * config.transaction_cost
        net_return = (1.0 + gross_return) * (1.0 - cost_rate) - 1.0
        equity_value *= 1.0 + net_return
        strategy_returns.loc[date] = net_return
        turnovers.loc[date] = traded
        current = target.copy()
        weights.loc[date] = current

        peak_value = max(peak_value, equity_value)
        drawdown = equity_value / peak_value - 1.0
        risk_exit_signal = (
            config.max_drawdown_limit is not None
            and drawdown <= -config.max_drawdown_limit
            and bool(current.abs().sum())
        )
        is_rebalance_signal = index % config.rebalance_every == 0
        pending_target = None
        if index + 1 < len(close):
            if risk_exit_signal:
                pending_target = pd.Series(0.0, index=close.columns)
                cooldown_left = config.cooldown_days
                peak_value = equity_value
            elif cooldown_left > 0:
                pending_target = pd.Series(0.0, index=close.columns)
                cooldown_left -= 1
            elif is_rebalance_signal:
                ranking = score.loc[date].dropna().nlargest(config.top_n).index
                pending_target = pd.Series(0.0, index=close.columns)
                if len(ranking):
                    pending_target.loc[ranking] = 1.0 / len(ranking)

        if (is_rebalance_signal or risk_exit_signal) and index > 0:
            period_returns.append(equity_value / period_start_value - 1.0)
            period_start_value = equity_value

    equity = config.initial_capital * (1.0 + strategy_returns).cumprod()
    active = strategy_returns[strategy_returns.ne(0.0)]
    daily_std = strategy_returns.std()
    downside = strategy_returns[strategy_returns.lt(0.0)].std()
    metrics = {
        "total_return": float(equity.iloc[-1] / config.initial_capital - 1.0),
        "annualized_return": float((equity.iloc[-1] / config.initial_capital) ** (252 / len(equity)) - 1.0),
        "annualized_volatility": float(daily_std * np.sqrt(252)),
        "sharpe": float(strategy_returns.mean() / daily_std * np.sqrt(252)) if daily_std else 0.0,
        "sortino": float(strategy_returns.mean() / downside * np.sqrt(252)) if downside else 0.0,
        "max_drawdown": float((equity / equity.cummax() - 1.0).min()),
        "daily_win_rate": float(active.gt(0.0).mean()) if len(active) else 0.0,
        "rebalance_win_rate": float(np.mean(np.asarray(period_returns) > 0.0)) if period_returns else 0.0,
        "average_turnover": float(turnovers.mean()),
    }
    return RotationBacktestResult(equity, weights, strategy_returns, metrics)
