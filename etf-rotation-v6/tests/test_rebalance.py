import unittest

import pandas as pd
import yaml

from src.backtest import run_backtest


class RebalanceTest(unittest.TestCase):
    def test_first_day_has_no_exposure_and_costs_are_finite(self) -> None:
        prices = pd.read_csv("data/sample/etf_sample.csv", parse_dates=["date"])
        with open("config/strategy_v6.yaml", encoding="utf-8") as handle:
            config = yaml.safe_load(handle)
        result = run_backtest(prices, config)
        curve = result["equity_curve"]
        self.assertEqual(curve["turnover"].iloc[0], 0.0)
        self.assertTrue(curve[["return", "equity", "turnover"]].notna().all().all())


if __name__ == "__main__":
    unittest.main()
