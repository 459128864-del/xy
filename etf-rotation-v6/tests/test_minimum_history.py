import unittest
from copy import deepcopy

import pandas as pd
import yaml

from src.backtest import run_backtest
from src.scoring import score_factors


FACTOR_WEIGHTS = {
    "momentum": 0.5,
    "efficiency": 0.2,
    "low_volatility": 0.15,
    "low_drawdown": 0.15,
}


def factor_rows(symbol: str, dates: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame({
        "date": dates,
        "symbol": symbol,
        "momentum": 1.0,
        "efficiency": 1.0,
        "volatility": 0.1,
        "drawdown": 0.0,
    })


class MinimumHistoryTest(unittest.TestCase):
    def test_history_below_minimum_cannot_enter_ranking(self) -> None:
        dates = pd.date_range("2024-01-02", periods=5, freq="B")
        scored = score_factors(
            factor_rows("A", dates),
            FACTOR_WEIGHTS,
            minimum_history=5,
        )
        self.assertEqual(list(scored["date"]), [dates[4]])
        self.assertEqual(list(scored["history_count"]), [5])
        self.assertTrue(scored["eligible"].all())

    def test_staggered_listing_history_is_counted_per_symbol(self) -> None:
        dates = pd.date_range("2024-01-02", periods=6, freq="B")
        factors = pd.concat([
            factor_rows("OLD", dates),
            factor_rows("NEW", dates[3:]),
        ], ignore_index=True).sort_values(["symbol", "date"])
        scored = score_factors(factors, FACTOR_WEIGHTS, minimum_history=3)

        old_first = scored.loc[scored["symbol"].eq("OLD"), "date"].min()
        new_first = scored.loc[scored["symbol"].eq("NEW"), "date"].min()
        self.assertEqual(old_first, dates[2])
        self.assertEqual(new_first, dates[5])

    def test_missing_required_factor_remains_ineligible(self) -> None:
        dates = pd.date_range("2024-01-02", periods=3, freq="B")
        factors = factor_rows("A", dates)
        factors.loc[2, "momentum"] = float("nan")
        scored = score_factors(factors, FACTOR_WEIGHTS, minimum_history=3)
        self.assertTrue(scored.empty)

    def test_future_rows_do_not_change_past_eligibility_or_scores(self) -> None:
        dates = pd.date_range("2024-01-02", periods=6, freq="B")
        initial = factor_rows("A", dates[:4])
        extended = factor_rows("A", dates)
        initial_scored = score_factors(initial, FACTOR_WEIGHTS, minimum_history=3)
        extended_scored = score_factors(extended, FACTOR_WEIGHTS, minimum_history=3)
        pd.testing.assert_frame_equal(
            initial_scored.reset_index(drop=True),
            extended_scored.loc[extended_scored["date"].le(dates[3])].reset_index(drop=True),
        )

    def test_all_ineligible_assets_remain_cash_and_create_no_trades(self) -> None:
        prices = pd.DataFrame({
            "date": list(pd.date_range("2024-01-02", periods=5, freq="B")) * 2,
            "symbol": ["A"] * 5 + ["B"] * 5,
            "close": [100.0, 101.0, 102.0, 103.0, 104.0] * 2,
        })
        with open("config/strategy_v6.yaml", encoding="utf-8") as handle:
            config = yaml.safe_load(handle)
        config = deepcopy(config)
        config["strategy"]["minimum_history"] = 10
        result = run_backtest(prices, config)
        self.assertTrue(result["scores"].empty)
        self.assertTrue(result["targets"].empty)
        self.assertTrue(result["trade_log"].empty)
        self.assertTrue(result["equity_curve"]["equity"].eq(1.0).all())

    def test_invalid_minimum_history_is_rejected(self) -> None:
        factors = factor_rows("A", pd.date_range("2024-01-02", periods=2))
        with self.assertRaisesRegex(ValueError, "minimum_history"):
            score_factors(factors, FACTOR_WEIGHTS, minimum_history=0)


if __name__ == "__main__":
    unittest.main()
