import unittest

import numpy as np
import pandas as pd

from src.backtest import build_valuation_returns, drift_weights, validate_execution_prices
from src.factors import _efficiency


class MissingMarketDataTest(unittest.TestCase):
    def test_missing_return_for_held_asset_fails_fast(self) -> None:
        weights = pd.Series({"A": 0.5, "B": 0.0})
        returns = pd.Series({"A": np.nan, "B": 0.01})
        with self.assertRaisesRegex(ValueError, "held assets"):
            drift_weights(weights, returns)

    def test_missing_unheld_asset_is_allowed(self) -> None:
        weights = pd.Series({"A": 0.5, "B": 0.0})
        returns = pd.Series({"A": 0.01, "B": np.nan})
        drifted = drift_weights(weights, returns)
        self.assertAlmostEqual(drifted["A"], 0.505 / 1.005)
        self.assertEqual(drifted["B"], 0.0)

    def test_execution_without_close_price_fails_fast(self) -> None:
        with self.assertRaisesRegex(ValueError, "without close prices"):
            validate_execution_prices(
                pd.Series({"A": 0.5, "B": 0.0}),
                pd.Series({"A": np.nan, "B": 100.0}),
            )

    def test_suspension_valuation_is_zero_then_catches_up_on_resumption(self) -> None:
        prices = pd.DataFrame({"A": [100.0, np.nan, 110.0], "B": [np.nan, 50.0, 55.0]})
        returns = build_valuation_returns(prices)
        self.assertTrue(np.isnan(returns.loc[0, "A"]))
        self.assertEqual(returns.loc[1, "A"], 0.0)
        self.assertAlmostEqual(returns.loc[2, "A"], 0.10)
        self.assertTrue(np.isnan(returns.loc[1, "B"]))
        self.assertAlmostEqual(returns.loc[2, "B"], 0.10)

    def test_suspended_unchanged_holding_does_not_require_execution_price(self) -> None:
        validate_execution_prices(
            pd.Series({"A": 0.0, "B": 0.0}),
            pd.Series({"A": np.nan, "B": 100.0}),
        )

    def test_efficiency_warmup_is_missing_but_flat_observed_path_is_zero(self) -> None:
        result = _efficiency(pd.Series([100.0, 100.0, 100.0, 100.0]), window=2)
        self.assertTrue(result.iloc[0:2].isna().all())
        self.assertEqual(result.iloc[2], 0.0)
        self.assertEqual(result.iloc[3], 0.0)


if __name__ == "__main__":
    unittest.main()
