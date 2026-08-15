import unittest
from collections.abc import Mapping
from datetime import date
from typing import Any
from unittest.mock import patch
from urllib.error import URLError

from scripts.fetch_ths_real_data import build_ths_dataset
from src.data_provider.base import Adjustment
from src.data_provider.exceptions import (
    ProviderAuthenticationError,
    ProviderDataError,
    ProviderRequestError,
)
from src.data_provider.factory import create_price_provider
from src.data_provider.ths_auth import THSCredentials
from src.data_provider.ths_http_transport import (
    THS_GET_ACCESS_TOKEN_PATH,
    THS_HISTORY_PATH,
    THS_REALTIME_PATH,
    THSHTTPPriceTransport,
    UrllibTHSJSONHTTPClient,
    from_ths_code,
    to_ths_code,
)
from src.data_provider.ths_price_provider import THSPriceProvider


class FakeHTTPClient:
    def __init__(self, *responses: Mapping[str, Any]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def post_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any] | None,
    ) -> Mapping[str, Any]:
        self.calls.append(
            {"url": url, "headers": dict(headers), "payload": payload}
        )
        if not self.responses:
            raise AssertionError("unexpected HTTP request")
        return self.responses.pop(0)


def history_response() -> dict[str, Any]:
    return {
        "errorcode": 0,
        "tables": [
            {
                "thscode": "510300.SH",
                "time": ["2026-07-30", "2026-07-31"],
                "table": {
                    "open": [4.10, 4.20],
                    "high": [4.20, 4.30],
                    "low": [4.00, 4.10],
                    "close": [4.15, 4.25],
                    "volume": [1000, 1100],
                    "amount": [4150, 4675],
                    "ths_af_stock": [1.01, 1.02],
                },
            }
        ],
    }


def realtime_response() -> dict[str, Any]:
    return {
        "errorcode": 0,
        "tables": [
            {
                "thscode": "159915.SZ",
                "table": {
                    "tradeDate": ["2026-08-03"],
                    "tradeTime": ["10:15:00"],
                    "preClose": [2.10],
                    "open": [2.11],
                    "high": [2.15],
                    "low": [2.09],
                    "latest": [2.14],
                    "latestVolume": [2000],
                    "latestAmount": [4280],
                },
            }
        ],
    }


class THSHTTPTransportTest(unittest.TestCase):
    def test_credentials_require_access_or_refresh_token(self) -> None:
        with self.assertRaises(ProviderAuthenticationError):
            THSCredentials.from_environment({})
        with self.assertRaises(ProviderAuthenticationError):
            THSCredentials.from_environment(
                {"THS_ACCESS_TOKEN": "  ", "THS_REFRESH_TOKEN": "\t"}
            )
        credentials = THSCredentials.from_environment(
            {"THS_ACCESS_TOKEN": " access-placeholder "}
        )
        self.assertEqual(credentials.access_token, "access-placeholder")
        self.assertNotIn("access-placeholder", repr(credentials))

    def test_symbol_conversion_is_explicit(self) -> None:
        self.assertEqual(to_ths_code("510300"), "510300.SH")
        self.assertEqual(to_ths_code("159915"), "159915.SZ")
        self.assertEqual(from_ths_code("510300.SH"), "510300")
        with self.assertRaises(ValueError):
            to_ths_code("000001")

    def test_history_request_and_response_use_canonical_schema(self) -> None:
        client = FakeHTTPClient(history_response())
        provider = THSPriceProvider(
            THSCredentials(access_token="access-placeholder"),
            transport=THSHTTPPriceTransport(http_client=client),
        )
        frame = provider.get_daily_price(
            ["510300"],
            start_date=date(2026, 7, 30),
            end_date=date(2026, 7, 31),
            adjustment=Adjustment.FORWARD,
        )

        self.assertEqual(frame["symbol"].tolist(), ["510300", "510300"])
        self.assertEqual(frame["close"].tolist(), [4.15, 4.25])
        self.assertEqual(frame["adjust_factor"].tolist(), [1.01, 1.02])
        call = client.calls[0]
        self.assertTrue(call["url"].endswith(THS_HISTORY_PATH))
        self.assertEqual(call["headers"]["access_token"], "access-placeholder")
        self.assertEqual(call["payload"]["codes"], "510300.SH")
        self.assertEqual(call["payload"]["functionpara"]["CPS"], "2")
        self.assertEqual(call["payload"]["functionpara"]["Fill"], "Blank")
        self.assertIn("volume", call["payload"]["indicators"])
        self.assertIn("amount", call["payload"]["indicators"])

    def test_history_requests_are_split_below_cell_limit_without_overlap(self) -> None:
        client = FakeHTTPClient(
            {"errorcode": -4001},
            {"errorcode": -4001},
            {"errorcode": -4001},
        )
        provider = THSPriceProvider(
            THSCredentials(access_token="access-placeholder"),
            transport=THSHTTPPriceTransport(
                http_client=client,
                max_history_cells_per_request=14,
            ),
        )
        frame = provider.get_daily_price(
            ["510300"],
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 5),
        )

        self.assertTrue(frame.empty)
        ranges = [
            (call["payload"]["startdate"], call["payload"]["enddate"])
            for call in client.calls
        ]
        self.assertEqual(
            ranges,
            [
                ("2026-08-01", "2026-08-02"),
                ("2026-08-03", "2026-08-04"),
                ("2026-08-05", "2026-08-05"),
            ],
        )

    def test_realtime_response_maps_timestamp_and_quote_fields(self) -> None:
        client = FakeHTTPClient(realtime_response())
        provider = THSPriceProvider(
            THSCredentials(access_token="access-placeholder"),
            transport=THSHTTPPriceTransport(http_client=client),
        )
        frame = provider.get_realtime_price(["159915"])

        self.assertEqual(frame.loc[0, "symbol"], "159915")
        self.assertEqual(frame.loc[0, "last"], 2.14)
        self.assertEqual(frame.loc[0, "volume"], 2000)
        self.assertEqual(frame.loc[0, "amount"], 4280)
        self.assertEqual(
            frame.loc[0, "timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
            "2026-08-03 10:15:00",
        )
        self.assertTrue(client.calls[0]["url"].endswith(THS_REALTIME_PATH))
        self.assertIn("latestVolume", client.calls[0]["payload"]["indicators"])
        self.assertIn("latestAmount", client.calls[0]["payload"]["indicators"])

    def test_refresh_token_is_used_only_when_access_token_is_missing(self) -> None:
        client = FakeHTTPClient(
            {"data": {"access_token": "current-access-placeholder"}},
            history_response(),
        )
        provider = THSPriceProvider(
            THSCredentials(refresh_token="refresh-placeholder"),
            transport=THSHTTPPriceTransport(http_client=client),
        )
        provider.get_daily_price(
            ["510300"],
            start_date=date(2026, 7, 30),
            end_date=date(2026, 7, 31),
        )

        self.assertTrue(client.calls[0]["url"].endswith(THS_GET_ACCESS_TOKEN_PATH))
        self.assertEqual(
            client.calls[0]["headers"]["refresh_token"], "refresh-placeholder"
        )
        self.assertNotIn("access_token", client.calls[0]["headers"])
        self.assertEqual(
            client.calls[1]["headers"]["access_token"],
            "current-access-placeholder",
        )

    def test_expired_access_token_retries_once_with_current_token(self) -> None:
        client = FakeHTTPClient(
            {"errorcode": -1302, "errmsg": "expired"},
            {"data": {"access_token": "renewed-access-placeholder"}},
            history_response(),
        )
        provider = THSPriceProvider(
            THSCredentials(
                access_token="expired-access-placeholder",
                refresh_token="refresh-placeholder",
            ),
            transport=THSHTTPPriceTransport(http_client=client),
        )
        frame = provider.get_daily_price(
            ["510300"],
            start_date=date(2026, 7, 30),
            end_date=date(2026, 7, 31),
        )

        self.assertEqual(len(frame), 2)
        self.assertEqual(len(client.calls), 3)
        self.assertEqual(
            client.calls[2]["headers"]["access_token"],
            "renewed-access-placeholder",
        )

    def test_expired_access_token_without_refresh_fails_safely(self) -> None:
        client = FakeHTTPClient({"errorcode": -1302, "errmsg": "secret text"})
        provider = THSPriceProvider(
            THSCredentials(access_token="expired-access-placeholder"),
            transport=THSHTTPPriceTransport(http_client=client),
        )
        with self.assertRaisesRegex(ProviderAuthenticationError, "-1302"):
            provider.get_daily_price(
                ["510300"],
                start_date=date(2026, 7, 30),
                end_date=date(2026, 7, 31),
            )

    def test_provider_error_does_not_echo_server_message(self) -> None:
        client = FakeHTTPClient(
            {"errorcode": -1202, "errmsg": "do-not-expose-this-message"}
        )
        provider = THSPriceProvider(
            THSCredentials(access_token="access-placeholder"),
            transport=THSHTTPPriceTransport(http_client=client),
        )
        with self.assertRaises(ProviderDataError) as caught:
            provider.get_realtime_price(["510300"])
        self.assertNotIn("do-not-expose", str(caught.exception))

    def test_http_transport_error_suppresses_secret_request_context(self) -> None:
        client = UrllibTHSJSONHTTPClient()
        with patch(
            "src.data_provider.ths_http_transport.urlopen",
            side_effect=URLError("network failure"),
        ):
            with self.assertRaises(ProviderRequestError) as caught:
                client.post_json(
                    "https://quantapi.51ifind.com/api/v1/real_time_quotation",
                    headers={"access_token": "do-not-expose-this-token"},
                    payload={"codes": "510300.SH", "indicators": "latest"},
                )
        self.assertEqual(str(caught.exception), "THS HTTP request failed")
        self.assertTrue(caught.exception.__suppress_context__)
        self.assertNotIn("do-not-expose", str(caught.exception))

    def test_response_cannot_add_an_unrequested_security(self) -> None:
        client = FakeHTTPClient(history_response())
        provider = THSPriceProvider(
            THSCredentials(access_token="access-placeholder"),
            transport=THSHTTPPriceTransport(http_client=client),
        )
        with self.assertRaisesRegex(ProviderDataError, "unrequested security"):
            provider.get_daily_price(
                ["159915"],
                start_date=date(2026, 7, 30),
                end_date=date(2026, 7, 31),
            )

    def test_factory_attaches_http_transport_without_requesting_data(self) -> None:
        provider = create_price_provider(
            "ths",
            environment={"THS_ACCESS_TOKEN": "access-placeholder"},
        )
        self.assertIsInstance(provider, THSPriceProvider)
        self.assertIsInstance(provider._transport, THSHTTPPriceTransport)

    def test_fixed_universe_dataset_enters_existing_data_pipeline(self) -> None:
        client = FakeHTTPClient(history_response())
        provider = THSPriceProvider(
            THSCredentials(access_token="access-placeholder"),
            transport=THSHTTPPriceTransport(http_client=client),
        )
        config = {
            "universe_scope": "fixed_research_universe",
            "start_date": "20260730",
            "end_date": "20260731",
            "adjust": "qfq",
            "universe": [
                {
                    "symbol": "510300",
                    "name": "沪深300ETF",
                    "category": "china_large_cap",
                }
            ],
        }
        prices, summary = build_ths_dataset(config, provider)

        self.assertEqual(summary["rows"], 2)
        self.assertEqual(summary["symbols"], 1)
        self.assertEqual(prices["name"].unique().tolist(), ["沪深300ETF"])
        self.assertEqual(
            prices["source"].unique().tolist(), ["tonghuashun_ifind_http"]
        )

    def test_all_etf_mode_is_rejected_until_universe_protocol_is_confirmed(self) -> None:
        config = {
            "universe_scope": "point_in_time_all_sh_sz_etfs",
            "start_date": "20260730",
            "end_date": "20260731",
            "adjust": "qfq",
            "universe": [{"symbol": "510300", "name": "ETF", "category": "x"}],
        }
        provider = THSPriceProvider(
            THSCredentials(access_token="access-placeholder"),
            transport=THSHTTPPriceTransport(http_client=FakeHTTPClient()),
        )
        with self.assertRaisesRegex(ValueError, "Universe protocol is not confirmed"):
            build_ths_dataset(config, provider)


if __name__ == "__main__":
    unittest.main()
