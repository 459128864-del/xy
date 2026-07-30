import unittest

import pandas as pd

from src.portfolio import construct_weights


class PositionLimitsTest(unittest.TestCase):
    def test_position_and_total_exposure_limits(self) -> None:
        scored = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-01"] * 3),
            "symbol": ["A", "B", "C"],
            "score": [0.9, 0.8, 0.7],
            "rank": [1.0, 2.0, 3.0],
        })
        regimes = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-01"]),
            "regime": ["balanced"],
        })
        weights = construct_weights(
            scored, regimes, top_n=2, min_score=0.5, max_position=0.4,
            exposure_by_regime={"balanced": 0.7},
        )
        self.assertLessEqual(weights["weight"].max(), 0.4)
        self.assertLessEqual(weights["weight"].sum(), 0.7)


if __name__ == "__main__":
    unittest.main()
