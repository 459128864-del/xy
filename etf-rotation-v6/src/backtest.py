"""Point-in-time ETF rotation backtest engine."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .portfolio import construct_weights
from .regime import classify_regime
from .risk_control import DrawdownGuard
from .scoring import score_factors
from .factors import calculate_factors


def build_execution_schedule(
    target_matrix: pd.DataFrame,
    rebalance_frequency: int,
) -> dict[pd.Timestamp, tuple[pd.Timestamp, pd.Series]]:
    """Map each rebalance signal to the next available close execution."""
    schedule: dict[pd.Timestamp, tuple[pd.Timestamp, pd.Series]] = {}
    dates = target_matrix.index
    for signal_index in range(0, len(dates), rebalance_frequency):
        execution_index = signal_index + 1
        if execution_index >= len(dates):
            continue
        signal_date = dates[signal_index]
        execution_date = dates[execution_index]
        schedule[execution_date] = (signal_date, target_matrix.loc[signal_date].copy())
    return schedule


def drift_weights(
    previous_weights: pd.Series,
    asset_returns: pd.Series,
) -> pd.Series:
    """Return pre-trade close weights after asset returns and zero-return cash."""
    aligned_returns = asset_returns.reindex(previous_weights.index).fillna(0.0)
    cash_weight = 1.0 - float(previous_weights.sum())
    portfolio_gross_factor = cash_weight + float(
        (previous_weights * (1.0 + aligned_returns)).sum()
    )
    if portfolio_gross_factor <= 0.0:
        raise ValueError("portfolio gross value must remain positive")
    return previous_weights * (1.0 + aligned_returns) / portfolio_gross_factor


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
    scored = score_factors(
        factors,
        factor_cfg["weights"],
        minimum_history=int(strategy["minimum_history"]),
    )
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
    execution_schedule = build_execution_schedule(target_matrix, rebalance)

    guard = DrawdownGuard(risk_cfg["max_portfolio_drawdown"], risk_cfg["cooldown_days"])
    equity = 1.0
    current_weights = pd.Series(0.0, index=returns.columns)
    current_target = pd.Series(0.0, index=returns.columns)
    current_risk_multiplier = 1.0
    records = []
    trade_records: list[dict[str, object]] = []
    open_position_dates: dict[str, int] = {}
    completed_holding_periods: list[int] = []
    commission_rate = float(risk_cfg["transaction_cost"])
    slippage_rate = float(risk_cfg.get("slippage_bps", 5.0)) / 10_000.0
    epsilon = 1e-12
    previous_date = pd.NaT
    for date_index, date in enumerate(returns.index):
        # The weights held before this close earn the return ending at this close.
        daily_return = float((current_weights * returns.loc[date]).sum())
        pre_trade_weights = drift_weights(current_weights, returns.loc[date])

        signal_date = None
        if date in execution_schedule:
            signal_date, current_target = execution_schedule[date]

        risk_multiplier = guard.exposure_multiplier(equity)
        risk_signal_date = previous_date if risk_multiplier != current_risk_multiplier else None
        should_trade = signal_date is not None or risk_signal_date is not None

        # Orders execute at this close and only affect the next close-to-close return.
        desired = (
            current_target * risk_multiplier
            if should_trade
            else pre_trade_weights
        )
        weight_changes = desired - pre_trade_weights
        turnover = float(weight_changes.abs().sum()) if should_trade else 0.0
        commission = turnover * commission_rate
        slippage = turnover * slippage_rate
        total_cost = commission + slippage
        net_return = daily_return - total_cost
        equity *= 1.0 + net_return
        records.append((
            date,
            previous_date,
            date,
            net_return,
            equity,
            turnover,
            commission,
            slippage,
            total_cost,
        ))

        event_signal_date = signal_date if signal_date is not None else risk_signal_date
        if should_trade:
            for asset in weight_changes.index[weight_changes.abs().gt(epsilon)]:
                asset_turnover = abs(float(weight_changes[asset]))
                asset_commission = asset_turnover * commission_rate
                asset_slippage = asset_turnover * slippage_rate
                previous_weight = float(pre_trade_weights[asset])
                target_weight = float(desired[asset])
                trade_records.append({
                    "signal_date": event_signal_date,
                    "execution_date": date,
                    "asset": asset,
                    "side": "buy" if weight_changes[asset] > 0.0 else "sell",
                    "previous_weight": previous_weight,
                    "target_weight": target_weight,
                    "turnover": asset_turnover,
                    "commission": asset_commission,
                    "slippage": asset_slippage,
                    "total_cost": asset_commission + asset_slippage,
                    "execution_price_type": "close",
                })
                if previous_weight <= epsilon < target_weight:
                    open_position_dates[asset] = date_index
                elif previous_weight > epsilon >= target_weight:
                    if asset in open_position_dates:
                        completed_holding_periods.append(
                            date_index - open_position_dates.pop(asset)
                        )
        current_weights = desired
        current_risk_multiplier = risk_multiplier
        previous_date = date

    curve = pd.DataFrame(records, columns=[
        "date",
        "return_start_date",
        "return_end_date",
        "return",
        "equity",
        "turnover",
        "commission",
        "slippage",
        "total_cost",
    ])
    trade_log = pd.DataFrame(trade_records, columns=[
        "signal_date",
        "execution_date",
        "asset",
        "side",
        "previous_weight",
        "target_weight",
        "turnover",
        "commission",
        "slippage",
        "total_cost",
        "execution_price_type",
    ])
    drawdown = curve["equity"].div(curve["equity"].cummax()).sub(1.0)
    volatility = curve["return"].std(ddof=0)
    metrics = {
        "total_return": float(curve["equity"].iloc[-1] - 1.0),
        "annualized_volatility": float(volatility * np.sqrt(252)),
        "sharpe": float(curve["return"].mean() / volatility * np.sqrt(252))
        if volatility > 0 else 0.0,
        "max_drawdown": float(drawdown.min()),
        "average_turnover": float(curve["turnover"].mean()),
        "trade_count": int(len(trade_log)),
        "buy_count": int(trade_log["side"].eq("buy").sum()),
        "sell_count": int(trade_log["side"].eq("sell").sum()),
        "average_holding_period": (
            float(np.mean(completed_holding_periods))
            if completed_holding_periods else 0.0
        ),
        "average_turnover_per_trade": (
            float(trade_log["turnover"].mean()) if not trade_log.empty else 0.0
        ),
        "cumulative_commission": float(curve["commission"].sum()),
        "cumulative_slippage": float(curve["slippage"].sum()),
        "cumulative_cost": float(curve["total_cost"].sum()),
    }
    return {
        "metrics": metrics,
        "equity_curve": curve,
        "execution_events": trade_log,
        "trade_log": trade_log,
        "targets": targets,
        "scores": scored,
    }
