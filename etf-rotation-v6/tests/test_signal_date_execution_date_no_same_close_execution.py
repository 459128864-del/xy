import unittest
from copy import deepcopy
from unittest.mock import patch

import pandas as pd

from src.backtest import build_execution_schedule, drift_weights, run_backtest


class SignalDateExecutionDateNoSameCloseExecutionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dates = pd.date_range("2024-01-02", periods=6, freq="B")
        self.prices = pd.DataFrame({
            "date": self.dates,
            "symbol": ["A"] * 6,
            "close": [100.0, 110.0, 121.0, 133.1, 146.41, 161.051],
        })
        self.config = {
            "strategy": {"rebalance_frequency": 2, "top_n": 1},
            "factors": {
                "momentum_windows": [1],
                "momentum_weights": [1.0],
                "skip_recent": 0,
                "efficiency_window": 1,
                "volatility_window": 1,
                "drawdown_window": 1,
                "weights": {
                    "momentum": 1.0,
                    "efficiency": 0.0,
                    "low_volatility": 0.0,
                    "low_drawdown": 0.0,
                },
            },
            "regime": {
                "trend_window": 1,
                "breadth_threshold": 0.5,
                "exposure": {"attack": 1.0},
            },
            "portfolio": {"min_score": 0.0, "max_position": 1.0},
            "risk": {
                "max_portfolio_drawdown": 1.0,
                "cooldown_days": 1,
                "transaction_cost": 0.0,
                "slippage_bps": 0,
            },
        }

    def _run_with_targets(self, weights: list[float]) -> dict[str, object]:
        targets = pd.DataFrame({
            "date": self.dates,
            "symbol": ["A"] * len(self.dates),
            "weight": weights,
            "regime": ["attack"] * len(self.dates),
        })
        placeholder = pd.DataFrame()
        with (
            patch("src.backtest.calculate_factors", return_value=placeholder),
            patch("src.backtest.score_factors", return_value=placeholder),
            patch("src.backtest.classify_regime", return_value=placeholder),
            patch("src.backtest.construct_weights", return_value=targets),
        ):
            return run_backtest(self.prices, self.config)

    def _run_custom_prices_and_targets(
        self,
        prices: pd.DataFrame,
        targets: pd.DataFrame,
        config: dict | None = None,
    ) -> dict[str, object]:
        placeholder = pd.DataFrame()
        with (
            patch("src.backtest.calculate_factors", return_value=placeholder),
            patch("src.backtest.score_factors", return_value=placeholder),
            patch("src.backtest.classify_regime", return_value=placeholder),
            patch("src.backtest.construct_weights", return_value=targets),
        ):
            return run_backtest(prices, config or self.config)

    def test_signal_date_cannot_affect_return_ending_on_execution_date(self) -> None:
        result = self._run_with_targets([1.0] * 6)
        curve = result["equity_curve"].set_index("date")
        self.assertEqual(curve.loc[self.dates[1], "return"], 0.0)

    def test_execution_date_weight_affects_only_next_return_interval(self) -> None:
        result = self._run_with_targets([1.0] * 6)
        curve = result["equity_curve"].set_index("date")
        self.assertAlmostEqual(curve.loc[self.dates[2], "return"], 0.1)
        self.assertEqual(curve.loc[self.dates[2], "return_start_date"], self.dates[1])
        self.assertEqual(curve.loc[self.dates[2], "return_end_date"], self.dates[2])
        event = result["execution_events"].iloc[0]
        self.assertEqual(event["signal_date"], self.dates[0])
        self.assertEqual(event["execution_date"], self.dates[1])

    def test_no_same_close_execution_on_rebalance_and_non_rebalance_dates(self) -> None:
        result = self._run_with_targets([1.0, 0.0, 0.5, 0.0, 0.25, 0.0])
        events = result["execution_events"]
        self.assertEqual(list(events["signal_date"].drop_duplicates()), list(self.dates[::2]))
        self.assertEqual(list(events["execution_date"].drop_duplicates()), list(self.dates[1::2]))
        self.assertAlmostEqual(
            result["equity_curve"].set_index("date").loc[self.dates[2], "return"],
            0.1,
        )

    def test_last_signal_date_without_execution_date_does_not_execute(self) -> None:
        matrix = pd.DataFrame({"A": [0.0] * 5}, index=self.dates[:5])
        schedule = build_execution_schedule(matrix, rebalance_frequency=2)
        signal_dates = [signal_date for signal_date, _ in schedule.values()]
        self.assertNotIn(self.dates[4], signal_dates)
        self.assertNotIn(self.dates[4], schedule)

    def test_consecutive_signal_date_execution_date_pairs_are_unique(self) -> None:
        result = self._run_with_targets([1.0, 0.0, 0.5, 0.0, 0.25, 0.0])
        pairs = result["execution_events"][["signal_date", "execution_date"]].drop_duplicates()
        self.assertEqual(len(pairs), 3)
        self.assertEqual(len(pairs), len(pairs.drop_duplicates()))
        self.assertTrue((pairs["execution_date"] > pairs["signal_date"]).all())

    def test_signal_date_execution_date_results_are_reproducible(self) -> None:
        first = self._run_with_targets([1.0] * 6)
        second = self._run_with_targets([1.0] * 6)
        pd.testing.assert_frame_equal(first["equity_curve"], second["equity_curve"])
        pd.testing.assert_frame_equal(first["execution_events"], second["execution_events"])

    def test_old_weight_earns_return_until_execution_date_before_new_weight(self) -> None:
        prices = pd.DataFrame({
            "date": list(self.dates) * 2,
            "symbol": ["A"] * 6 + ["B"] * 6,
            "close": [
                100.0, 100.0, 100.0, 110.0, 110.0, 110.0,
                100.0, 100.0, 100.0, 150.0, 165.0, 165.0,
            ],
        })
        targets = pd.DataFrame({
            "date": [date for date in self.dates for _ in range(2)],
            "symbol": ["A", "B"] * 6,
            "weight": [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0],
            "regime": ["attack"] * 12,
        })
        result = self._run_custom_prices_and_targets(prices, targets)
        curve = result["equity_curve"].set_index("date")

        # The d2 signal switches A to B at d3 close. A earns d2->d3;
        # B's d2->d3 jump must not enter the portfolio return.
        self.assertAlmostEqual(curve.loc[self.dates[3], "return"], 0.1)
        self.assertAlmostEqual(curve.loc[self.dates[4], "return"], 0.1)

    def test_turnover_uses_drifted_weights_at_execution_date(self) -> None:
        prices = pd.DataFrame({
            "date": list(self.dates) * 2,
            "symbol": ["A"] * 6 + ["B"] * 6,
            "close": [
                100.0, 100.0, 200.0, 200.0, 200.0, 200.0,
                100.0, 100.0, 100.0, 100.0, 100.0, 100.0,
            ],
        })
        targets = pd.DataFrame({
            "date": [date for date in self.dates for _ in range(2)],
            "symbol": ["A", "B"] * 6,
            "weight": [0.5, 0.5] * 6,
            "regime": ["attack"] * 12,
        })
        result = self._run_custom_prices_and_targets(prices, targets)
        curve = result["equity_curve"].set_index("date")
        events = result["execution_events"]
        second_execution = events[events["execution_date"].eq(self.dates[3])]

        # After A doubles and B is flat, actual weights are 2/3 and 1/3.
        # Returning to 50/50 requires two-sided turnover of 1/3.
        self.assertAlmostEqual(curve.loc[self.dates[3], "turnover"], 1.0 / 3.0)
        self.assertAlmostEqual(
            second_execution.loc[second_execution["asset"].eq("A"), "previous_weight"].iloc[0],
            2.0 / 3.0,
        )
        self.assertAlmostEqual(
            second_execution.loc[second_execution["asset"].eq("B"), "previous_weight"].iloc[0],
            1.0 / 3.0,
        )

    def test_non_rebalance_date_uses_naturally_drifted_weights(self) -> None:
        weights = pd.Series({"A": 0.5, "B": 0.5})
        first_drift = drift_weights(weights, pd.Series({"A": 1.0, "B": 0.0}))
        second_return = float((first_drift * pd.Series({"A": 0.1, "B": 0.0})).sum())
        self.assertAlmostEqual(first_drift["A"], 2.0 / 3.0)
        self.assertAlmostEqual(first_drift["B"], 1.0 / 3.0)
        self.assertAlmostEqual(second_return, (2.0 / 3.0) * 0.1)

    def test_partial_exposure_drift_preserves_zero_return_cash(self) -> None:
        for exposure in (0.35, 0.70):
            with self.subTest(exposure=exposure):
                weights = pd.Series({"A": exposure / 2.0, "B": exposure / 2.0})
                drifted = drift_weights(weights, pd.Series({"A": 1.0, "B": 0.0}))
                gross_factor = (1.0 - exposure) + exposure / 2.0 * 2.0 + exposure / 2.0
                self.assertAlmostEqual(drifted["A"], exposure / gross_factor)
                self.assertAlmostEqual(drifted["B"], (exposure / 2.0) / gross_factor)
                self.assertLess(float(drifted.sum()), 1.0)

    def test_zero_returns_preserve_weights_and_unchanged_target_has_no_trade(self) -> None:
        prices = pd.DataFrame({
            "date": list(self.dates) * 2,
            "symbol": ["A"] * 6 + ["B"] * 6,
            "close": [100.0] * 12,
        })
        targets = pd.DataFrame({
            "date": [date for date in self.dates for _ in range(2)],
            "symbol": ["A", "B"] * 6,
            "weight": [0.5, 0.5] * 6,
            "regime": ["attack"] * 12,
        })
        result = self._run_custom_prices_and_targets(prices, targets)
        curve = result["equity_curve"].set_index("date")
        events = result["execution_events"]
        self.assertEqual(curve.loc[self.dates[3], "turnover"], 0.0)
        self.assertFalse(events["execution_date"].eq(self.dates[3]).any())

    def test_exit_and_entry_events_use_asset_union_weights(self) -> None:
        prices = pd.DataFrame({
            "date": list(self.dates) * 2,
            "symbol": ["A"] * 6 + ["B"] * 6,
            "close": [100.0] * 12,
        })
        targets = pd.DataFrame({
            "date": [date for date in self.dates for _ in range(2)],
            "symbol": ["A", "B"] * 6,
            "weight": [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0],
            "regime": ["attack"] * 12,
        })
        result = self._run_custom_prices_and_targets(prices, targets)
        second = result["execution_events"]
        second = second[second["execution_date"].eq(self.dates[3])].set_index("asset")
        self.assertEqual(set(second.index), {"A", "B"})
        self.assertEqual(second.loc["A", "previous_weight"], 1.0)
        self.assertEqual(second.loc["A", "target_weight"], 0.0)
        self.assertEqual(second.loc["B", "previous_weight"], 0.0)
        self.assertEqual(second.loc["B", "target_weight"], 1.0)

    def test_consecutive_daily_signal_dates_execute_without_overwrite(self) -> None:
        config = deepcopy(self.config)
        config["strategy"]["rebalance_frequency"] = 1
        targets = pd.DataFrame({
            "date": self.dates,
            "symbol": ["A"] * 6,
            "weight": [1.0, 0.5, 0.25, 0.75, 0.0, 1.0],
            "regime": ["attack"] * 6,
        })
        result = self._run_custom_prices_and_targets(self.prices, targets, config)
        pairs = result["execution_events"][["signal_date", "execution_date"]].drop_duplicates()
        self.assertEqual(list(pairs["signal_date"]), list(self.dates[:-1]))
        self.assertEqual(list(pairs["execution_date"]), list(self.dates[1:]))
        self.assertTrue((pairs["execution_date"] > pairs["signal_date"]).all())


if __name__ == "__main__":
    unittest.main()
