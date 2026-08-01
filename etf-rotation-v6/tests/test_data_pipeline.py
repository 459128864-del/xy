import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.data_pipeline import (
    fetch_universe, load_historical_universe, point_in_time_universe,
    require_survivorship_controlled, validate_historical_coverage,
    validate_price_data, write_dataset,
)


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
            self.assertFalse(manifest["historical_universe_complete"])
            self.assertFalse(manifest["survivorship_bias_controlled"])
            with self.assertRaisesRegex(ValueError, "survivorship"):
                require_survivorship_controlled(manifest)

    def test_complete_historical_manifest_passes_research_claim_gate(self) -> None:
        require_survivorship_controlled({
            "historical_universe_complete": True,
            "survivorship_bias_controlled": True,
            "historical_catalog_sha256": "a" * 64,
            "historical_catalog_metadata": {
                "scope": "all_sh_sz_etfs", "authoritative": True,
                "source_name": "exchange", "source_url": "https://example.test",
                "complete_through": "2024-01-31",
                "expected_symbol_count": 2,
            },
            "historical_coverage": {
                "eligible_symbols": 2, "observed_symbols": 2,
                "catalog_symbols": 2, "delisted_symbols": 1,
            },
        })

    def test_boolean_claim_without_catalog_evidence_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "survivorship"):
            require_survivorship_controlled({
                "historical_universe_complete": True,
                "survivorship_bias_controlled": True,
            })

    def test_current_only_catalog_cannot_claim_survivorship_control(self) -> None:
        with self.assertRaisesRegex(ValueError, "survivorship"):
            require_survivorship_controlled({
                "historical_universe_complete": True,
                "survivorship_bias_controlled": True,
                "historical_catalog_sha256": "a" * 64,
                "historical_catalog_metadata": {
                    "scope": "all_sh_sz_etfs", "authoritative": True,
                    "source_name": "current list",
                    "source_url": "https://example.test/current",
                    "complete_through": "2024-01-31",
                    "expected_symbol_count": 2,
                },
                "historical_coverage": {
                    "eligible_symbols": 2, "observed_symbols": 2,
                    "catalog_symbols": 2, "delisted_symbols": 0,
                },
            })

    def test_point_in_time_universe_includes_then_removes_delisted_etf(self) -> None:
        catalog = pd.DataFrame({
            "symbol": ["ACTIVE", "DELISTED", "NEW"],
            "listing_date": pd.to_datetime([
                "2020-01-01", "2020-01-01", "2024-01-04"
            ]),
            "delisting_date": pd.to_datetime([None, "2024-01-03", None]),
        })
        self.assertEqual(
            point_in_time_universe(catalog, "2024-01-02"),
            {"ACTIVE", "DELISTED"},
        )
        self.assertEqual(
            point_in_time_universe(catalog, "2024-01-03"),
            {"ACTIVE"},
        )
        self.assertEqual(
            point_in_time_universe(catalog, "2024-01-04"),
            {"ACTIVE", "NEW"},
        )

    def test_historical_coverage_requires_delisted_price_history(self) -> None:
        catalog = pd.DataFrame({
            "symbol": ["ACTIVE", "DELISTED"],
            "name": ["Active", "Delisted"],
            "listing_date": pd.to_datetime(["2020-01-01", "2020-01-01"]),
            "delisting_date": pd.to_datetime([None, "2024-01-03"]),
            "source": ["exchange", "exchange"],
        })
        prices = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "symbol": ["ACTIVE", "ACTIVE"],
            "close": [1.0, 1.1],
        }).sort_values(["symbol", "date"]).reset_index(drop=True)
        with self.assertRaisesRegex(ValueError, "DELISTED"):
            validate_historical_coverage(
                prices, catalog, start_date="2024-01-01", end_date="2024-01-31"
            )

    def test_validated_catalog_writes_evidence_backed_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            catalog_path = directory_path / "catalog.csv"
            catalog_path.write_text(
                "symbol,name,listing_date,delisting_date,source\n"
                "A,Alpha,2020-01-01,,exchange\n"
                "B,Beta,2020-01-01,2024-01-05,exchange\n",
                encoding="utf-8",
            )
            catalog = load_historical_universe(catalog_path)
            prices, summary = fetch_universe(self.config, self.fetcher)
            output = directory_path / "prices.csv"
            manifest_path = directory_path / "manifest.json"
            write_dataset(
                prices,
                summary,
                output_path=output,
                manifest_path=manifest_path,
                config=self.config,
                historical_catalog=catalog,
                catalog_metadata={
                    "scope": "all_sh_sz_etfs",
                    "authoritative": True,
                    "complete_through": "2024-01-31",
                    "source_name": "test exchange catalogue",
                    "source_url": "https://example.test/catalog",
                    "expected_symbol_count": 2,
                },
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertTrue(manifest["survivorship_bias_controlled"])
            self.assertEqual(manifest["historical_coverage"]["delisted_symbols"], 1)
            require_survivorship_controlled(manifest)


if __name__ == "__main__":
    unittest.main()
