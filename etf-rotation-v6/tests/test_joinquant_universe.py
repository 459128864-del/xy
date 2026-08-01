import unittest
from datetime import date

import pandas as pd

from src.joinquant_universe import (
    build_joinquant_metadata, fetch_joinquant_etf_catalog,
    normalize_joinquant_etf_catalog,
)


class JoinQuantUniverseTest(unittest.TestCase):
    @staticmethod
    def raw_catalog() -> pd.DataFrame:
        return pd.DataFrame({
            "display_name": ["Active ETF", "Delisted ETF", "A LOF"],
            "name": ["ACTIVE", "OLD", "LOF"],
            "start_date": [date(2020, 1, 2), date(2011, 3, 28), date(2010, 1, 1)],
            "end_date": [date(2200, 1, 1), date(2022, 12, 27), date(2200, 1, 1)],
            "type": ["etf", "etf", "lof"],
        }, index=["510300.XSHG", "510220.XSHG", "160000.XSHE"])

    def test_normalizes_etfs_and_active_sentinel(self) -> None:
        catalog = normalize_joinquant_etf_catalog(self.raw_catalog())
        self.assertEqual(catalog["symbol"].tolist(), ["510220", "510300"])
        self.assertTrue(catalog.loc[catalog["symbol"].eq("510300"), "delisting_date"].isna().all())
        self.assertEqual(
            catalog.loc[catalog["symbol"].eq("510220"), "delisting_date"].iloc[0],
            pd.Timestamp("2022-12-27"),
        )

    def test_fetch_uses_all_dates_and_requires_known_delisted_etf(self) -> None:
        calls = []

        def fetcher(**kwargs):
            calls.append(kwargs)
            return self.raw_catalog()

        catalog = fetch_joinquant_etf_catalog(fetcher)
        self.assertEqual(calls, [{"types": ["fund"], "date": None}])
        self.assertEqual(len(catalog), 2)

    def test_current_only_response_is_rejected(self) -> None:
        current = self.raw_catalog().drop(index="510220.XSHG")
        with self.assertRaisesRegex(ValueError, "510220"):
            fetch_joinquant_etf_catalog(lambda **_: current)

    def test_metadata_matches_catalog_count(self) -> None:
        catalog = normalize_joinquant_etf_catalog(self.raw_catalog())
        metadata = build_joinquant_metadata(catalog, as_of=date(2026, 8, 1))
        self.assertEqual(metadata["scope"], "all_sh_sz_etfs")
        self.assertEqual(metadata["provider_id"], "joinquant_jqdata")
        self.assertEqual(metadata["expected_symbol_count"], 2)
        self.assertEqual(metadata["complete_through"], "2026-08-01")


if __name__ == "__main__":
    unittest.main()
