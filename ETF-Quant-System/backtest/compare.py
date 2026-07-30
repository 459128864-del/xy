"""Compare baseline and risk-controlled ETF rotation strategies."""

import argparse
from pathlib import Path

import pandas as pd

from backtest.rotation_engine import RotationBacktestConfig, run_rotation_backtest
from strategy.optimized_rotation import (
    OptimizedRotationConfig,
    baseline_trend_scores,
    optimized_rotation_scores,
)


def compare_strategies(
    prices: pd.DataFrame,
    top_n: int = 3,
    rebalance_every: int = 5,
    volatility_quantile: float = 0.70,
    max_drawdown_limit: float = 0.08,
) -> pd.DataFrame:
    """Return baseline-vs-optimized metrics on the exact same price sample."""
    baseline = baseline_trend_scores(prices)
    optimized = optimized_rotation_scores(
        prices,
        OptimizedRotationConfig(volatility_quantile=volatility_quantile),
    )
    common = dict(top_n=top_n, rebalance_every=rebalance_every)
    before = run_rotation_backtest(
        prices, baseline, RotationBacktestConfig(**common)
    )
    after = run_rotation_backtest(
        prices,
        optimized,
        RotationBacktestConfig(
            **common,
            max_drawdown_limit=max_drawdown_limit,
            cooldown_days=10,
        ),
    )
    comparison = pd.DataFrame(
        {"优化前": before.metrics, "优化后": after.metrics}
    )
    comparison["变化"] = comparison["优化后"] - comparison["优化前"]
    return comparison


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("prices", type=Path, help="CSV with date,symbol,close")
    parser.add_argument("--output", type=Path, default=Path("comparison.csv"))
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--rebalance-every", type=int, default=5)
    parser.add_argument("--volatility-quantile", type=float, default=0.70)
    parser.add_argument("--max-drawdown", type=float, default=0.08)
    args = parser.parse_args()

    prices = pd.read_csv(args.prices, parse_dates=["date"])
    comparison = compare_strategies(
        prices,
        top_n=args.top_n,
        rebalance_every=args.rebalance_every,
        volatility_quantile=args.volatility_quantile,
        max_drawdown_limit=args.max_drawdown,
    )
    comparison.to_csv(args.output, encoding="utf-8-sig")
    print(comparison.round(4).to_string())


if __name__ == "__main__":
    main()
