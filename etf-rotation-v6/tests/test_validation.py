import unittest

import pandas as pd

from src.validation import build_annual_windows, classify_benchmark_regime, return_metrics


class ValidationTest(unittest.TestCase):
    def test_annual_oos_windows_do_not_overlap(self) -> None:
        dates = pd.date_range("2010-01-01", "2020-12-31", freq="B")
        windows = build_annual_windows(dates, train_years=5, test_years=1, step_years=1)
        for left, right in zip(windows, windows[1:]):
            self.assertLess(left.test_end, right.test_start)
            self.assertLess(left.train_end, left.test_start)

    def test_rolling_training_start_moves_but_expanding_does_not(self) -> None:
        dates = pd.date_range("2010-01-01", "2020-12-31", freq="B")
        rolling = build_annual_windows(dates, train_years=5)
        expanding = build_annual_windows(dates, train_years=5, expanding=True)
        self.assertGreater(rolling[1].train_start, rolling[0].train_start)
        self.assertEqual(expanding[1].train_start, expanding[0].train_start)

    def test_regime_uses_trailing_not_future_return(self) -> None:
        base = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=5), "close": [100, 101, 102, 103, 104]})
        changed = base.copy()
        changed.loc[4, "close"] = 1000
        kwargs = {"lookback_days": 2, "bull_threshold": 0.01, "bear_threshold": -0.01}
        original = classify_benchmark_regime(base, **kwargs)
        revised = classify_benchmark_regime(changed, **kwargs)
        pd.testing.assert_series_equal(original.loc[:3, "market_regime"], revised.loc[:3, "market_regime"])

    def test_return_metrics_are_deterministic(self) -> None:
        values = pd.Series([0.01, -0.01, 0.02])
        self.assertEqual(return_metrics(values), return_metrics(values.copy()))


if __name__ == "__main__":
    unittest.main()
