import unittest

import numpy as np
import pandas as pd

from backtest.compare import compare_strategies
from strategy.optimized_rotation import optimized_rotation_scores


def sample_prices() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2023-01-02", periods=180)
    rows = []
    for index, symbol in enumerate(["A", "B", "C", "D", "E"]):
        shocks = rng.normal(0.0003 + index * 0.0001, 0.004 + index * 0.003, len(dates))
        close = 100 * np.exp(np.cumsum(shocks))
        rows.extend(zip(dates, [symbol] * len(dates), close))
    return pd.DataFrame(rows, columns=["date", "symbol", "close"])


class OptimizedRotationTest(unittest.TestCase):
    def test_filter_and_comparison(self) -> None:
        prices = sample_prices()
        signals = optimized_rotation_scores(prices)
        self.assertTrue(
            signals.loc[signals["eligible"], "volatility_pass"].all()
        )
        self.assertTrue(signals.loc[signals["eligible"], "trend_pass"].all())

        comparison = compare_strategies(prices)
        self.assertEqual(list(comparison.columns), ["优化前", "优化后", "变化"])
        self.assertTrue(
            {
                "daily_win_rate",
                "rebalance_win_rate",
                "max_drawdown",
                "sharpe",
            }.issubset(comparison.index)
        )
        self.assertTrue(np.isfinite(comparison.to_numpy()).all())


if __name__ == "__main__":
    unittest.main()
