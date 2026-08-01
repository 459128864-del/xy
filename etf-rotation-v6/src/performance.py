"""Point-in-time benchmark comparison utilities."""

from __future__ import annotations

import numpy as np
import pandas as pd


def compare_with_benchmark(
    equity_curve: pd.DataFrame,
    benchmark_prices: pd.DataFrame,
    *,
    periods_per_year: int = 252,
) -> tuple[dict[str, float | int | str], pd.DataFrame]:
    """Compare strategy and benchmark on common dates, without filling gaps."""
    benchmark = benchmark_prices.loc[:, ["date", "close"]].copy()
    benchmark["date"] = pd.to_datetime(benchmark["date"], errors="raise")
    if benchmark["date"].duplicated().any() or benchmark["close"].le(0).any():
        raise ValueError("benchmark dates must be unique and closes positive")
    strategy = equity_curve.loc[:, ["date", "return", "equity"]].copy()
    strategy["date"] = pd.to_datetime(strategy["date"], errors="raise")
    aligned = strategy.merge(benchmark, on="date", how="inner", validate="one_to_one")
    aligned = aligned.sort_values("date").reset_index(drop=True)
    if len(aligned) < 2:
        raise ValueError("benchmark comparison requires at least two common dates")
    aligned["benchmark_return"] = aligned["close"].pct_change(fill_method=None)
    aligned = aligned.dropna(subset=["benchmark_return"]).reset_index(drop=True)
    aligned["benchmark_equity"] = (1.0 + aligned["benchmark_return"]).cumprod()
    aligned["excess_return"] = aligned["return"] - aligned["benchmark_return"]
    years = len(aligned) / periods_per_year
    strategy_total = float((1.0 + aligned["return"]).prod() - 1.0)
    benchmark_total = float(aligned["benchmark_equity"].iloc[-1] - 1.0)
    excess_vol = float(aligned["excess_return"].std(ddof=0))
    symbol = benchmark_prices["symbol"].iloc[0] if "symbol" in benchmark_prices else "unknown"
    metrics: dict[str, float | int | str] = {
        "benchmark_symbol": str(symbol),
        "comparison_start_date": aligned["date"].iloc[0].date().isoformat(),
        "comparison_end_date": aligned["date"].iloc[-1].date().isoformat(),
        "comparison_observations": int(len(aligned)),
        "strategy_total_return_aligned": strategy_total,
        "benchmark_total_return": benchmark_total,
        "excess_total_return": strategy_total - benchmark_total,
        "strategy_annualized_return_aligned": float((1.0 + strategy_total) ** (1.0 / years) - 1.0),
        "benchmark_annualized_return": float((1.0 + benchmark_total) ** (1.0 / years) - 1.0),
        "tracking_error": excess_vol * np.sqrt(periods_per_year),
        "information_ratio": (
            float(aligned["excess_return"].mean() / excess_vol * np.sqrt(periods_per_year))
            if excess_vol > 0 else 0.0
        ),
    }
    return metrics, aligned
