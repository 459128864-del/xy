import unittest

import pandas as pd

from backtest.engine import BacktestConfig, run_backtest
from backtest.rotation_engine import RotationBacktestConfig, run_rotation_backtest


def long_prices(a, b):
    dates = pd.date_range("2024-01-01", periods=len(a), freq="D")
    return pd.DataFrame(
        [(date, symbol, value) for symbol, values in [("A", a), ("B", b)] for date, value in zip(dates, values)],
        columns=["date", "symbol", "close"],
    )


class BacktestAccountingTest(unittest.TestCase):
    def test_signal_executes_next_close_and_only_affects_following_return(self):
        prices = long_prices([100, 200, 220], [100, 100, 100])
        signals = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=3, freq="D"),
            "symbol": ["A", "A", "A"], "score": [1.0, 1.0, 1.0],
        })
        result = run_backtest(prices, signals, BacktestConfig(top_n=1, rebalance_every=5, transaction_cost=0.0))
        self.assertEqual(result.equity.iloc[1], 1_000_000.0)
        self.assertAlmostEqual(result.equity.iloc[2], 1_100_000.0)

    def test_empty_rebalance_signal_executes_full_cash(self):
        prices = long_prices([100, 101, 102, 103], [100, 100, 100, 100])
        signals = pd.DataFrame({"date": [pd.Timestamp("2024-01-01")], "symbol": ["A"], "score": [1.0]})
        result = run_backtest(prices, signals, BacktestConfig(top_n=1, rebalance_every=2, transaction_cost=0.0))
        self.assertEqual(result.weights.loc[pd.Timestamp("2024-01-04")].sum(), 0.0)

    def test_non_rebalance_weights_drift_naturally(self):
        prices = long_prices([100, 100, 200], [100, 100, 100])
        dates = pd.date_range("2024-01-01", periods=3, freq="D")
        signals = pd.DataFrame({
            "date": [dates[0], dates[0]], "symbol": ["A", "B"], "score": [2.0, 1.0],
        })
        result = run_backtest(prices, signals, BacktestConfig(top_n=2, rebalance_every=5, transaction_cost=0.0))
        self.assertAlmostEqual(result.weights.loc[dates[2], "A"], 2 / 3)
        self.assertAlmostEqual(result.weights.loc[dates[2], "B"], 1 / 3)

    def test_rotation_engine_equity_matches_its_return_series(self):
        prices = long_prices([100, 101, 102, 103], [100, 99, 100, 101])
        dates = pd.date_range("2024-01-01", periods=4, freq="D")
        signals = pd.DataFrame({"date": dates, "symbol": ["A"] * 4, "score": [1.0] * 4})
        config = RotationBacktestConfig(top_n=1, rebalance_every=2, transaction_cost=0.001)
        result = run_rotation_backtest(prices, signals, config)
        expected = config.initial_capital * (1.0 + result.returns).cumprod()
        pd.testing.assert_series_equal(result.equity, expected)

    def test_suspension_is_flat_then_full_move_is_recognized_on_resumption(self):
        prices = long_prices([100, 100, float("nan"), 110], [100, 100, 100, 100])
        signals = pd.DataFrame({
            "date": [pd.Timestamp("2024-01-01")], "symbol": ["A"], "score": [1.0],
        })
        result = run_backtest(prices, signals, BacktestConfig(top_n=1, rebalance_every=5, transaction_cost=0.0))
        self.assertEqual(result.equity.loc[pd.Timestamp("2024-01-03")], 1_000_000.0)
        self.assertAlmostEqual(result.equity.loc[pd.Timestamp("2024-01-04")], 1_100_000.0)


if __name__ == "__main__":
    unittest.main()
