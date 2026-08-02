import unittest
from datetime import date

import pandas as pd

from src.joinquant_universe import (
    build_joinquant_metadata, build_joinquant_price_fetcher,
    fetch_joinquant_etf_catalog, normalize_joinquant_etf_catalog,
    to_joinquant_security,
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

    def test_exchange_symbol_mapping_is_explicit(self) -> None:
        self.assertEqual(to_joinquant_security("510300"), "510300.XSHG")
        self.assertEqual(to_joinquant_security("159915"), "159915.XSHE")
        with self.assertRaises(ValueError):
            to_joinquant_security("000300")

    def test_price_fetcher_uses_pre_adjustment_and_skips_paused_fill(self) -> None:
        calls = []

        def get_price(*args, **kwargs):
            calls.append((args, kwargs))
            return pd.DataFrame(
                {"close": [1.0, 1.1]},
                index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
            )

        fetcher = build_joinquant_price_fetcher(get_price)
        result = fetcher(
            symbol="510300", period="daily", start_date="20240101",
            end_date="20240131", adjust="qfq",
        )
        self.assertEqual(list(result.columns), ["日期", "收盘"])
        self.assertEqual(calls[0][0], ("510300.XSHG",))
        self.assertTrue(calls[0][1]["skip_paused"])
        self.assertEqual(calls[0][1]["fq"], "pre")


if __name__ == "__main__":
    unittest.main()
