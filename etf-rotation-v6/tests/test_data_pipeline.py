import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.data_pipeline import fetch_universe, validate_price_data, write_dataset


class DataPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = {
            "provider": "akshare",
            "interface": "fund_etf_hist_em",
            "period": "daily",
            "adjust": "qfq",
            "start_date": "20240101",
            "end_date": "20240131",
            "universe": [
                {"symbol": "A", "name": "Alpha", "category": "equity"},
                {"symbol": "B", "name": "Beta", "category": "bond"},
            ],
        }

    @staticmethod
    def fetcher(symbol: str, **_: object) -> pd.DataFrame:
        dates = ["2024-01-02", "2024-01-03", "2024-01-04"]
        if symbol == "B":
            dates = dates[1:]
        return pd.DataFrame({"日期": dates, "收盘": range(100, 100 + len(dates))})

    def test_fetch_normalizes_and_preserves_listing_start(self) -> None:
        prices, summary = fetch_universe(self.config, self.fetcher)
        self.assertEqual(list(prices.columns), [
            "date", "close", "symbol", "name", "category", "source", "adjustment"
        ])
        self.assertEqual(summary["symbols"], 2)
        b_start = prices.loc[prices["symbol"].eq("B"), "date"].min()
        self.assertEqual(b_start, pd.Timestamp("2024-01-03"))
        self.assertTrue(prices["adjustment"].eq("qfq").all())

    def test_duplicate_observations_are_rejected(self) -> None:
        prices, _ = fetch_universe(self.config, self.fetcher)
        duplicate = pd.concat([prices, prices.iloc[[0]]], ignore_index=True)
        duplicate = duplicate.sort_values(["symbol", "date"]).reset_index(drop=True)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_price_data(duplicate)

    def test_nonpositive_close_is_rejected(self) -> None:
        prices, _ = fetch_universe(self.config, self.fetcher)
        prices.loc[0, "close"] = 0.0
        with self.assertRaisesRegex(ValueError, "positive"):
            validate_price_data(prices)

    def test_manifest_contains_hash_and_quality_summary(self) -> None:
        prices, summary = fetch_universe(self.config, self.fetcher)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "prices.csv"
            manifest_path = Path(directory) / "manifest.json"
            write_dataset(
                prices,
                summary,
                output_path=output,
                manifest_path=manifest_path,
                config=self.config,
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["sha256"]), 64)
            self.assertEqual(manifest["summary"], summary)
            self.assertEqual(manifest["adjustment"], "qfq")


if __name__ == "__main__":
    unittest.main()
