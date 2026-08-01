"""Simple cross-sectional ETF rotation backtest with explicit close execution."""

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


def drift_weights(previous: pd.Series, returns: pd.Series) -> pd.Series:
    """Drift risky assets while retaining zero-return cash."""
    aligned = returns.reindex(previous.index)
    held_missing = previous.gt(0.0) & aligned.isna()
    if held_missing.any():
        raise ValueError(f"missing return for held assets: {list(previous.index[held_missing])}")
    aligned = aligned.fillna(0.0)
    cash = 1.0 - float(previous.sum())
    gross_factor = cash + float((previous * (1.0 + aligned)).sum())
    if gross_factor <= 0.0:
        raise ValueError("portfolio gross value must remain positive")
    return previous * (1.0 + aligned) / gross_factor


def validate_execution(weight_changes: pd.Series, raw_close: pd.Series) -> None:
    unavailable = weight_changes.abs().gt(1e-12) & raw_close.reindex(
        weight_changes.index
    ).isna()
    if unavailable.any():
        raise ValueError(
            f"cannot execute without close prices: {list(weight_changes.index[unavailable])}"
        )


def run_backtest(
    prices: pd.DataFrame,
    scores: pd.DataFrame,
    config: BacktestConfig = BacktestConfig(),
) -> BacktestResult:
    """Execute each rebalance signal at the following trading day's close."""
    if config.top_n < 1 or config.rebalance_every < 1:
        raise ValueError("top_n and rebalance_every must be positive")
    close = prices.pivot(index="date", columns="symbol", values="close").sort_index()
    score = scores.pivot(index="date", columns="symbol", values="score").reindex(
        index=close.index, columns=close.columns
    )
    asset_returns = close.ffill().pct_change(fill_method=None)
    weights = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    strategy_returns = pd.Series(0.0, index=close.index, name="return")
    turnover = pd.Series(0.0, index=close.index, name="turnover")
    current = pd.Series(0.0, index=close.columns)
    pending_target: pd.Series | None = None

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
        strategy_returns.loc[date] = (1.0 + gross_return) * (1.0 - cost_rate) - 1.0
        turnover.loc[date] = traded
        current = target.copy()
        weights.loc[date] = current

        pending_target = None
        if index % config.rebalance_every == 0 and index + 1 < len(close):
            ranking = score.loc[date].dropna().nlargest(config.top_n).index
            next_target = pd.Series(0.0, index=close.columns)
            if len(ranking):
                next_target.loc[ranking] = 1.0 / len(ranking)
            pending_target = next_target

    equity = config.initial_capital * (1.0 + strategy_returns).cumprod()
    daily_std = strategy_returns.std()
    metrics = {
        "total_return": float(equity.iloc[-1] / config.initial_capital - 1.0),
        "annualized_return": float(
            (equity.iloc[-1] / config.initial_capital) ** (252 / max(len(equity), 1)) - 1.0
        ),
        "annualized_volatility": float(daily_std * np.sqrt(252)),
        "sharpe": float(strategy_returns.mean() / daily_std * np.sqrt(252)) if daily_std else 0.0,
        "max_drawdown": float((equity / equity.cummax() - 1.0).min()),
        "average_turnover": float(turnover.mean()),
    }
    return BacktestResult(equity=equity, weights=weights, metrics=metrics)
