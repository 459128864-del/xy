import unittest

import pandas as pd

from src.factors import calculate_factors


class FactorMathTest(unittest.TestCase):
    def test_efficiency_is_one_for_monotonic_path(self) -> None:
        prices = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=12),
            "symbol": "A",
            "close": range(100, 112),
        })
        result = calculate_factors(
            prices, momentum_windows=[3], momentum_weights=[1.0], skip_recent=0,
            efficiency_window=5, volatility_window=3, drawdown_window=5,
        )
        self.assertAlmostEqual(result["efficiency"].iloc[-1], 1.0)
        self.assertAlmostEqual(result["drawdown"].iloc[-1], 0.0)


if __name__ == "__main__":
    unittest.main()
