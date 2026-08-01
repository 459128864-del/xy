import unittest
from copy import deepcopy
from unittest.mock import patch

import pandas as pd

from src.backtest import run_backtest


class SlippageAndTradeLedgerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dates = pd.date_range("2024-01-02", periods=4, freq="B")
        self.prices = pd.DataFrame({
            "date": self.dates,
            "symbol": ["A"] * 4,
            "close": [100.0] * 4,
        })
        self.targets = pd.DataFrame({
            "date": self.dates,
            "symbol": ["A"] * 4,
            "weight": [1.0] * 4,
            "regime": ["attack"] * 4,
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
                "transaction_cost": 0.001,
                "slippage_bps": 5,
            },
        }

    def _run(
        self,
        *,
        config: dict | None = None,
        targets: pd.DataFrame | None = None,
    ) -> dict[str, object]:
        placeholder = pd.DataFrame()
        with (
            patch("src.backtest.calculate_factors", return_value=placeholder),
            patch("src.backtest.score_factors", return_value=placeholder),
            patch("src.backtest.classify_regime", return_value=placeholder),
            patch(
                "src.backtest.construct_weights",
                return_value=self.targets if targets is None else targets,
            ),
        ):
            return run_backtest(self.prices, config or self.config)

    def test_commission_and_slippage_are_accumulated_separately(self) -> None:
        result = self._run()
        metrics = result["metrics"]
        self.assertAlmostEqual(metrics["cumulative_commission"], 0.001)
        self.assertAlmostEqual(metrics["cumulative_slippage"], 0.0005)
        self.assertAlmostEqual(metrics["cumulative_cost"], 0.0015)

    def test_zero_slippage_matches_commission_only_result(self) -> None:
        config = deepcopy(self.config)
        config["risk"]["slippage_bps"] = 0
        result = self._run(config=config)
        self.assertAlmostEqual(result["equity_curve"]["equity"].iloc[-1], 0.999)
        self.assertEqual(result["metrics"]["cumulative_slippage"], 0.0)
        self.assertAlmostEqual(result["metrics"]["cumulative_cost"], 0.001)

    def test_higher_slippage_cannot_increase_net_return(self) -> None:
        zero_config = deepcopy(self.config)
        zero_config["risk"]["slippage_bps"] = 0
        zero_result = self._run(config=zero_config)
        slippage_result = self._run()
        self.assertLessEqual(
            slippage_result["metrics"]["total_return"],
            zero_result["metrics"]["total_return"],
        )

    def test_trade_log_cost_columns_are_consistent(self) -> None:
        result = self._run()
        trade_log = result["trade_log"]
        self.assertEqual(list(trade_log["side"]), ["buy"])
        self.assertTrue(
            (
                trade_log["commission"]
                + trade_log["slippage"]
                - trade_log["total_cost"]
            ).abs().lt(1e-15).all()
        )
        self.assertAlmostEqual(
            trade_log["turnover"].sum(),
            result["equity_curve"]["turnover"].sum(),
        )

    def test_zero_trade_produces_no_trade_log_or_cost(self) -> None:
        zero_targets = self.targets.copy()
        zero_targets["weight"] = 0.0
        result = self._run(targets=zero_targets)
        self.assertTrue(result["trade_log"].empty)
        self.assertEqual(result["metrics"]["trade_count"], 0)
        self.assertEqual(result["metrics"]["cumulative_cost"], 0.0)

    def test_trade_statistics_include_holding_period_and_sides(self) -> None:
        config = deepcopy(self.config)
        config["strategy"]["rebalance_frequency"] = 1
        targets = self.targets.copy()
        targets["weight"] = [1.0, 0.0, 0.0, 0.0]
        result = self._run(config=config, targets=targets)
        metrics = result["metrics"]
        self.assertEqual(metrics["trade_count"], 2)
        self.assertEqual(metrics["buy_count"], 1)
        self.assertEqual(metrics["sell_count"], 1)
        self.assertEqual(metrics["average_holding_period"], 1.0)
        self.assertAlmostEqual(metrics["average_turnover_per_trade"], 1.0)


if __name__ == "__main__":
    unittest.main()
