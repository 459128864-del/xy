"""Fixed-parameter out-of-sample and market-regime validation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .backtest import run_backtest


@dataclass(frozen=True)
class ValidationWindow:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


def build_annual_windows(
    dates: pd.Series | pd.DatetimeIndex,
    *,
    train_years: int,
    test_years: int = 1,
    step_years: int = 1,
    expanding: bool = False,
) -> list[ValidationWindow]:
    """Build non-overlapping calendar OOS windows from available dates."""
    index = pd.DatetimeIndex(pd.to_datetime(dates)).sort_values().unique()
    if train_years <= 0 or test_years <= 0 or step_years < test_years:
        raise ValueError("training/test years must be positive and test windows non-overlapping")
    first, last = index.min(), index.max()
    windows: list[ValidationWindow] = []
    test_start_boundary = first + pd.DateOffset(years=train_years)
    while test_start_boundary <= last:
        test_end_boundary = test_start_boundary + pd.DateOffset(years=test_years)
        test_dates = index[(index >= test_start_boundary) & (index < test_end_boundary)]
        if len(test_dates) == 0:
            test_start_boundary += pd.DateOffset(years=step_years)
            continue
        train_start_boundary = first if expanding else test_start_boundary - pd.DateOffset(years=train_years)
        train_dates = index[(index >= train_start_boundary) & (index < test_start_boundary)]
        if len(train_dates) == 0:
            raise ValueError("validation window has no training history")
        windows.append(ValidationWindow(
            train_start=train_dates.min(), train_end=train_dates.max(),
            test_start=test_dates.min(), test_end=test_dates.max(),
        ))
        test_start_boundary += pd.DateOffset(years=step_years)
    return windows


def return_metrics(returns: pd.Series, *, periods_per_year: int = 252) -> dict[str, float | int]:
    values = pd.Series(returns, dtype=float).dropna()
    if values.empty:
        raise ValueError("cannot calculate metrics from empty returns")
    equity = (1.0 + values).cumprod()
    years = len(values) / periods_per_year
    total = float(equity.iloc[-1] - 1.0)
    volatility = float(values.std(ddof=0))
    drawdown = equity.div(equity.cummax()).sub(1.0)
    return {
        "observations": int(len(values)),
        "total_return": total,
        "annualized_return": float((1.0 + total) ** (1.0 / years) - 1.0),
        "annualized_volatility": volatility * np.sqrt(periods_per_year),
        "sharpe": float(values.mean() / volatility * np.sqrt(periods_per_year)) if volatility > 0 else 0.0,
        "max_drawdown": float(drawdown.min()),
    }


def run_window_validation(
    prices: pd.DataFrame,
    config: dict,
    windows: list[ValidationWindow],
) -> list[dict[str, object]]:
    """Run fixed parameters with training history used only as warm-up."""
    results = []
    for window in windows:
        history = prices.loc[prices["date"].between(window.train_start, window.test_end)]
        backtest = run_backtest(history, config)
        curve = backtest["equity_curve"]
        oos = curve.loc[curve["date"].between(window.test_start, window.test_end)]
        metrics = return_metrics(oos["return"])
        results.append({
            "train_start": window.train_start.date().isoformat(),
            "train_end": window.train_end.date().isoformat(),
            "test_start": window.test_start.date().isoformat(),
            "test_end": window.test_end.date().isoformat(),
            **metrics,
        })
    return results


def classify_benchmark_regime(
    benchmark: pd.DataFrame,
    *,
    lookback_days: int,
    bull_threshold: float,
    bear_threshold: float,
) -> pd.DataFrame:
    """Classify each date using only trailing benchmark performance."""
    frame = benchmark.loc[:, ["date", "close"]].sort_values("date").copy()
    trailing = frame["close"].pct_change(lookback_days, fill_method=None)
    frame["market_regime"] = "sideways"
    frame.loc[trailing.ge(bull_threshold), "market_regime"] = "bull"
    frame.loc[trailing.le(bear_threshold), "market_regime"] = "bear"
    frame.loc[trailing.isna(), "market_regime"] = "insufficient_history"
    return frame.loc[:, ["date", "market_regime"]]


def regime_metrics(
    equity_curve: pd.DataFrame,
    benchmark: pd.DataFrame,
    regime_config: dict,
) -> dict[str, dict[str, float | int] | str]:
    regimes = classify_benchmark_regime(benchmark, **regime_config)
    joined = equity_curve.loc[:, ["date", "return"]].merge(regimes, on="date", how="inner")
    output: dict[str, dict[str, float | int] | str] = {}
    for name in ["bull", "sideways", "bear"]:
        values = joined.loc[joined["market_regime"].eq(name), "return"]
        output[name] = return_metrics(values) if not values.empty else "data_insufficient"
    return output
