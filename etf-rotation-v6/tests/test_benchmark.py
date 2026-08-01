import unittest

import pandas as pd

from src.performance import compare_with_benchmark


class BenchmarkTest(unittest.TestCase):
    def test_aligns_only_common_dates_without_forward_fill(self) -> None:
        curve = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
            "return": [0.0, 0.10, 0.0],
            "equity": [1.0, 1.1, 1.1],
        })
        benchmark = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-02", "2024-01-04"]),
            "close": [100.0, 110.0],
            "symbol": ["sh000300", "sh000300"],
        })
        metrics, aligned = compare_with_benchmark(curve, benchmark)
        self.assertEqual(metrics["comparison_observations"], 1)
        self.assertEqual(list(aligned["date"]), [pd.Timestamp("2024-01-04")])
        self.assertAlmostEqual(metrics["benchmark_total_return"], 0.10)
        self.assertAlmostEqual(metrics["strategy_total_return_aligned"], 0.0)

    def test_rejects_duplicate_dates(self) -> None:
        curve = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "return": [0.0, 0.0], "equity": [1.0, 1.0],
        })
        benchmark = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-02", "2024-01-02"]),
            "close": [100.0, 101.0],
        })
        with self.assertRaisesRegex(ValueError, "unique"):
            compare_with_benchmark(curve, benchmark)


if __name__ == "__main__":
    unittest.main()
