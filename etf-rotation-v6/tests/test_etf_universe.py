import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.data_provider.universe import (
    UNIVERSE_SCHEMA_VERSION,
    DataFrameETFUniverseProvider,
    UniverseValidationError,
    build_universe_manifest,
    write_universe_manifest,
)


def make_universe() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "instrument_id": ["etf-active", "etf-old", "etf-future"],
            "symbol": ["ACTIVE", "OLD", "FUTURE"],
            "name": ["Active ETF", "Old ETF", "Future ETF"],
            "exchange": ["SH", "SZ", "SH"],
            "list_date": ["2018-01-01", "2010-01-01", "2025-01-01"],
            "delist_date": [None, "2020-12-31", None],
            "category": ["equity_broad", "bond", "equity_theme"],
            "source": ["test"] * 3,
            "source_as_of": ["2026-08-02"] * 3,
        }
    )


class ETFUniverseTest(unittest.TestCase):
    def test_future_listing_is_excluded_from_historical_universe(self) -> None:
        provider = DataFrameETFUniverseProvider(make_universe())
        self.assertFalse(provider.is_available("FUTURE", "2020-01-01"))
        self.assertNotIn(
            "FUTURE", set(provider.get_active_universe("2020-01-01")["symbol"])
        )

    def test_delisted_etf_is_included_on_delist_date_then_removed(self) -> None:
        provider = DataFrameETFUniverseProvider(make_universe())
        self.assertTrue(provider.is_available("OLD", "2020-12-31"))
        self.assertFalse(provider.is_available("OLD", "2021-01-01"))

    def test_list_date_after_delist_date_is_rejected(self) -> None:
        universe = make_universe().iloc[[0]].copy()
        universe.loc[:, "list_date"] = "2021-01-01"
        universe.loc[:, "delist_date"] = "2020-12-31"
        with self.assertRaisesRegex(UniverseValidationError, "list_date"):
            DataFrameETFUniverseProvider(universe)

    def test_overlapping_symbol_lifecycles_are_rejected(self) -> None:
        universe = make_universe().iloc[[0]].copy()
        universe.loc[:, "delist_date"] = "2020-12-31"
        reused = universe.copy()
        reused.loc[:, "instrument_id"] = "etf-active-reused"
        reused.loc[:, "list_date"] = "2020-12-31"
        reused.loc[:, "delist_date"] = None
        with self.assertRaisesRegex(UniverseValidationError, "overlapping"):
            DataFrameETFUniverseProvider(pd.concat([universe, reused]))

    def test_duplicate_instrument_id_is_rejected(self) -> None:
        universe = make_universe().iloc[:2].copy()
        universe.loc[universe.index[1], "instrument_id"] = universe.iloc[0][
            "instrument_id"
        ]
        with self.assertRaisesRegex(UniverseValidationError, "instrument_id"):
            DataFrameETFUniverseProvider(universe)

    def test_manifest_contains_required_fields(self) -> None:
        manifest = build_universe_manifest(make_universe(), source="test")
        self.assertEqual(
            set(manifest),
            {
                "generated_at",
                "source",
                "universe_version",
                "instrument_count",
                "schema_version",
            },
        )
        self.assertEqual(len(manifest["universe_version"]), len("sha256:") + 64)

    def test_manifest_instrument_count_is_correct(self) -> None:
        manifest = build_universe_manifest(make_universe(), source="test")
        self.assertEqual(manifest["instrument_count"], 3)

    def test_manifest_schema_version_is_present(self) -> None:
        manifest = build_universe_manifest(make_universe(), source="test")
        self.assertEqual(manifest["schema_version"], UNIVERSE_SCHEMA_VERSION)

    def test_same_input_produces_identical_manifest(self) -> None:
        universe = make_universe()
        first = build_universe_manifest(universe, source="test")
        second = build_universe_manifest(
            universe.iloc[::-1].reset_index(drop=True), source="test"
        )
        self.assertEqual(first, second)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "etf_universe_manifest.json"
            write_universe_manifest(universe, source="test", output_path=path)
            first_bytes = path.read_bytes()
            write_universe_manifest(
                universe.iloc[::-1].reset_index(drop=True),
                source="test",
                output_path=path,
            )
            self.assertEqual(first_bytes, path.read_bytes())
            self.assertEqual(json.loads(first_bytes), first)


if __name__ == "__main__":
    unittest.main()
