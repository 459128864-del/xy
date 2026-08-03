import unittest
from datetime import date

import pandas as pd

from src.data_provider.base import Adjustment, PriceProvider
from src.data_provider.ths_auth import THSCredentials
from src.data_provider.ths_price_provider import THSPriceProvider
from src.data_provider.ths_universe_provider import THSETFUniverseProvider


def make_universe() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "instrument_id": ["etf-active", "etf-future"],
            "symbol": ["ACTIVE", "FUTURE"],
            "name": ["Active ETF", "Future ETF"],
            "exchange": ["SH", "SZ"],
            "list_date": ["2018-01-01", "2025-01-01"],
            "delist_date": [None, None],
            "category": ["equity_broad", "equity_theme"],
            "source": ["test", "test"],
            "source_as_of": ["2026-08-02", "2026-08-02"],
        }
    )


class FakeUniverseTransport:
    def get_all_etfs(self, *, credentials: THSCredentials) -> pd.DataFrame:
        return make_universe()


class FakePriceTransport:
    def get_daily_price(
        self,
        *,
        credentials: THSCredentials,
        symbols: tuple[str, ...],
        start_date: date,
        end_date: date,
        adjustment: Adjustment,
    ) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "date": [start_date],
                "symbol": [symbols[0]],
                "open": [1.0],
                "high": [1.1],
                "low": [0.9],
                "close": [1.0],
                "volume": [100.0],
                "amount": [100.0],
                "adjustment": [adjustment.value],
                "source": ["test"],
            }
        )

    def get_realtime_price(
        self, *, credentials: THSCredentials, symbols: tuple[str, ...]
    ) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "timestamp": ["2026-08-03 10:00:00"],
                "symbol": [symbols[0]],
                "last": [1.0],
                "open": [1.0],
                "high": [1.1],
                "low": [0.9],
                "previous_close": [0.99],
                "volume": [100.0],
                "amount": [100.0],
                "source": ["test"],
            }
        )


class DataProviderBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.credentials = THSCredentials("placeholder", "placeholder", "placeholder")

    def test_price_provider_contract_has_no_universe_operations(self) -> None:
        self.assertFalse(hasattr(PriceProvider, "get_etf_list"))
        self.assertFalse(hasattr(PriceProvider, "get_etf_info"))
        self.assertTrue(hasattr(PriceProvider, "get_daily_price"))
        self.assertTrue(hasattr(PriceProvider, "get_realtime_price"))

    def test_ths_price_provider_exposes_only_price_operations(self) -> None:
        provider = THSPriceProvider(
            self.credentials,
            transport=FakePriceTransport(),
        )
        self.assertFalse(hasattr(provider, "get_etf_list"))
        self.assertFalse(hasattr(provider, "get_all_etfs"))
        daily = provider.get_daily_price(
            ["ACTIVE"],
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 1),
        )
        self.assertEqual(list(daily["symbol"]), ["ACTIVE"])

    def test_ths_universe_provider_exposes_no_price_operations(self) -> None:
        provider = THSETFUniverseProvider(
            self.credentials,
            transport=FakeUniverseTransport(),
        )
        self.assertFalse(hasattr(provider, "get_daily_price"))
        self.assertFalse(hasattr(provider, "get_realtime_price"))
        self.assertTrue(provider.is_available("ACTIVE", "2020-01-01"))
        self.assertFalse(provider.is_available("FUTURE", "2020-01-01"))


if __name__ == "__main__":
    unittest.main()
