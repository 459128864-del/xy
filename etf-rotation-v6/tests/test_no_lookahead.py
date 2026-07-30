import unittest

import pandas as pd

from src.factors import calculate_factors


class NoLookaheadTest(unittest.TestCase):
    def test_future_price_change_does_not_change_past_factor(self) -> None:
        base = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=15),
            "symbol": "A",
            "close": [100 + index for index in range(15)],
        })
        changed = base.copy()
        changed.loc[14, "close"] = 1000
        kwargs = dict(
            momentum_windows=[3, 5], momentum_weights=[0.5, 0.5],
            skip_recent=1, efficiency_window=5, volatility_window=5,
            drawdown_window=5,
        )
        original = calculate_factors(base, **kwargs)
        revised = calculate_factors(changed, **kwargs)
        pd.testing.assert_series_equal(
            original.loc[:13, "momentum"], revised.loc[:13, "momentum"]
        )


if __name__ == "__main__":
    unittest.main()
