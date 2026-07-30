"""Point-in-time ETF rotation backtest engine."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .portfolio import construct_weights
from .regime import classify_regime
from .risk_control import DrawdownGuard
from .scoring import score_factors
from .factors import calculate_factors


def run_backtest(prices: pd.DataFrame, config: dict) -> dict[str, object]:
    strategy = config["strategy"]
    factor_cfg = config["factors"]
    risk_cfg = config["risk"]
    portfolio_cfg = config["portfolio"]

    factors = calculate_factors(
        prices,
        momentum_windows=factor_cfg["momentum_windows"],
        momentum_weights=factor_cfg["momentum_weights"],
        skip_recent=factor_cfg["skip_recent"],
        efficiency_window=factor_cfg["efficiency_window"],
        volatility_window=factor_cfg["volatility_window"],
        drawdown_window=factor_cfg["drawdown_window"],
    )
    scored = score_factors(factors, factor_cfg["weights"])
    regimes = classify_regime(prices, **{
        "trend_window": config["regime"]["trend_window"],
        "breadth_threshold": config["regime"]["breadth_threshold"],
    })
    targets = construct_weights(
        scored,
        regimes,
        top_n=strategy["top_n"],
        min_score=portfolio_cfg["min_score"],
        max_position=portfolio_cfg["max_position"],
        exposure_by_regime=config["regime"]["exposure"],
    )

    price_matrix = prices.pivot(index="date", columns="symbol", values="close").sort_index()
    returns = price_matrix.pct_change(fill_method=None).fillna(0.0)
    target_matrix = targets.pivot(index="date", columns="symbol", values="weight")
    target_matrix = target_matrix.reindex(index=returns.index, columns=returns.columns).fillna(0.0)
    rebalance = int(strategy["rebalance_frequency"])
    mask = pd.Series(np.arange(len(target_matrix)) % rebalance == 0, index=target_matrix.index)
    held_targets = target_matrix.where(mask, np.nan).ffill().fillna(0.0)
    positions = held_targets.shift(1).fillna(0.0)

    guard = DrawdownGuard(risk_cfg["max_portfolio_drawdown"], risk_cfg["cooldown_days"])
    equity = 1.0
    previous = pd.Series(0.0, index=positions.columns)
    records = []
    for date in returns.index:
        desired = positions.loc[date] * guard.exposure_multiplier(equity)
        turnover = (desired - previous).abs().sum()
        daily_return = float((desired * returns.loc[date]).sum())
        net_return = daily_return - turnover * float(risk_cfg["transaction_cost"])
        equity *= 1.0 + net_return
        records.append((date, net_return, equity, turnover))
        previous = desired

    curve = pd.DataFrame(records, columns=["date", "return", "equity", "turnover"])
    drawdown = curve["equity"].div(curve["equity"].cummax()).sub(1.0)
    volatility = curve["return"].std(ddof=0)
    metrics = {
        "total_return": float(curve["equity"].iloc[-1] - 1.0),
        "annualized_volatility": float(volatility * np.sqrt(252)),
        "sharpe": float(curve["return"].mean() / volatility * np.sqrt(252))
        if volatility > 0 else 0.0,
        "max_drawdown": float(drawdown.min()),
        "average_turnover": float(curve["turnover"].mean()),
    }
    return {"metrics": metrics, "equity_curve": curve, "targets": targets, "scores": scored}
