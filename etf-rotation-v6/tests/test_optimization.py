import unittest

from src.optimization import config_with_defense_exposure, select_development_candidate


class OptimizationTest(unittest.TestCase):
    def test_only_defense_exposure_changes(self) -> None:
        base = {"regime": {"exposure": {"attack": 1.0, "balanced": 0.7, "defense": 0.35}}, "factors": {"x": 1}}
        candidate = config_with_defense_exposure(base, 0.15)
        self.assertEqual(candidate["regime"]["exposure"]["defense"], 0.15)
        self.assertEqual(candidate["regime"]["exposure"]["attack"], 1.0)
        self.assertEqual(candidate["factors"], base["factors"])
        self.assertEqual(base["regime"]["exposure"]["defense"], 0.35)

    def test_selection_uses_only_development_metrics(self) -> None:
        rows = [
            {"exposure": 0.35, "metrics": {"annualized_return": 0.05, "sharpe": 0.5, "max_drawdown": -0.30}},
            {"exposure": 0.15, "metrics": {"annualized_return": 0.04, "sharpe": 0.45, "max_drawdown": -0.20}},
            {"exposure": 0.00, "metrics": {"annualized_return": -0.01, "sharpe": 0.7, "max_drawdown": -0.10}},
        ]
        selected = select_development_candidate(
            rows, baseline_exposure=0.35, minimum_annualized_return=0.0,
            maximum_sharpe_degradation_from_baseline=0.1,
        )
        self.assertEqual(selected["exposure"], 0.15)


if __name__ == "__main__":
    unittest.main()
