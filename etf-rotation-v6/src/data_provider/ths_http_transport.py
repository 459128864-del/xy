"""Official iFinD HTTP transport for THS historical and realtime prices.

Constructing this transport never performs a request.  Network access occurs
only when a caller explicitly asks the provider for prices.  Secrets stay in
request headers and are never included in exceptions or representations.
"""

from __future__ import annotations

import gzip
import json
import zlib
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd

from .base import Adjustment
from .exceptions import (
    ProviderAuthenticationError,
    ProviderDataError,
    ProviderRequestError,
)
from .ths_auth import THSCredentials


THS_API_BASE_URL = "https://quantapi.51ifind.com/api/v1"
THS_GET_ACCESS_TOKEN_PATH = "/get_access_token"
THS_HISTORY_PATH = "/cmd_history_quotation"
THS_REALTIME_PATH = "/real_time_quotation"

THS_HISTORY_INDICATORS = (
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "ths_af_stock",
)
THS_REALTIME_INDICATORS = (
    "tradeDate",
    "tradeTime",
    "preClose",
    "open",
    "high",
    "low",
    "latest",
    "latestVolume",
    "latestAmount",
)
THS_TOKEN_ERROR_CODES = {-1010, -1302}
THS_NO_DATA_ERROR_CODE = -4001

_CPS_BY_ADJUSTMENT = {
    Adjustment.NONE: "1",
    Adjustment.FORWARD: "2",
    Adjustment.BACKWARD: "3",
}


class THSJSONHTTPClient(Protocol):
    """Small injectable JSON boundary used by the real and fake transports."""

    def post_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any] | None,
    ) -> Mapping[str, Any]: ...


class UrllibTHSJSONHTTPClient:
    """Standard-library HTTP client so the provider adds no dependency."""

    def __init__(self, *, timeout_seconds: float = 30.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._timeout_seconds = float(timeout_seconds)

    def post_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any] | None,
    ) -> Mapping[str, Any]:
        body = b"" if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(url, data=body, headers=dict(headers), method="POST")
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                content = response.read()
                encoding = response.headers.get("Content-Encoding", "").lower()
        except (HTTPError, URLError, TimeoutError, OSError):
            # Do not chain urllib exceptions: request objects may retain secret
            # headers and can be printed by an uncaught traceback.
            raise ProviderRequestError("THS HTTP request failed") from None

        try:
            if encoding == "gzip":
                content = gzip.decompress(content)
            elif encoding == "deflate":
                content = zlib.decompress(content)
            decoded = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, OSError, zlib.error) as exc:
            raise ProviderDataError("THS HTTP response is not valid JSON") from exc
        if not isinstance(decoded, Mapping):
            raise ProviderDataError("THS HTTP response root must be an object")
        return decoded


class THSAccessTokenManager:
    """Keep the current access token in memory and refresh only when needed."""

    def __init__(
        self,
        credentials: THSCredentials,
        *,
        http_client: THSJSONHTTPClient,
        base_url: str = THS_API_BASE_URL,
    ) -> None:
        self._refresh_token = credentials.refresh_token
        self._access_token = credentials.access_token
        self._http_client = http_client
        self._base_url = base_url.rstrip("/")

    @property
    def can_refresh(self) -> bool:
        return bool(self._refresh_token)

    def invalidate(self) -> None:
        self._access_token = None

    def get_access_token(self) -> str:
        if self._access_token:
            return self._access_token
        if not self._refresh_token:
            raise ProviderAuthenticationError(
                "THS access token is unavailable and no refresh token was configured"
            )
        response = self._http_client.post_json(
            f"{self._base_url}{THS_GET_ACCESS_TOKEN_PATH}",
            headers={
                "Content-Type": "application/json",
                "refresh_token": self._refresh_token,
            },
            payload=None,
        )
        error_code = _error_code(response)
        if error_code not in (None, 0):
            raise ProviderAuthenticationError(
                f"THS access-token request failed with error code {error_code}"
            )
        data = response.get("data")
        token = data.get("access_token") if isinstance(data, Mapping) else None
        if not isinstance(token, str) or not token.strip():
            raise ProviderAuthenticationError(
                "THS access-token response did not contain an access token"
            )
        self._access_token = token.strip()
        return self._access_token


class THSHTTPPriceTransport:
    """Map official iFinD HTTP responses to canonical provider DataFrames."""

    def __init__(
        self,
        *,
        http_client: THSJSONHTTPClient | None = None,
        base_url: str = THS_API_BASE_URL,
        batch_size: int = 50,
        max_history_cells_per_request: int = 45_000,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if max_history_cells_per_request < len(THS_HISTORY_INDICATORS):
            raise ValueError(
                "max_history_cells_per_request cannot fit one symbol-day"
            )
        self._http_client = http_client or UrllibTHSJSONHTTPClient()
        self._base_url = base_url.rstrip("/")
        self._batch_size = int(batch_size)
        self._max_history_cells_per_request = int(
            max_history_cells_per_request
        )

    def get_daily_price(
        self,
        *,
        credentials: THSCredentials,
        symbols: Sequence[str],
        start_date: date,
        end_date: date,
        adjustment: Adjustment,
    ) -> pd.DataFrame:
        canonical_symbols = _canonical_symbols(symbols)
        if not canonical_symbols:
            return _empty_daily_frame()
        token_manager = THSAccessTokenManager(
            credentials,
            http_client=self._http_client,
            base_url=self._base_url,
        )
        frames: list[pd.DataFrame] = []
        for batch in _batches(canonical_symbols, self._batch_size):
            chunks = _history_date_chunks(
                start_date,
                end_date,
                symbol_count=len(batch),
                indicator_count=len(THS_HISTORY_INDICATORS),
                max_cells=self._max_history_cells_per_request,
            )
            for chunk_start, chunk_end in chunks:
                payload = {
                    "codes": ",".join(to_ths_code(symbol) for symbol in batch),
                    "indicators": ",".join(THS_HISTORY_INDICATORS),
                    "startdate": chunk_start.isoformat(),
                    "enddate": chunk_end.isoformat(),
                    "functionpara": {
                        "Interval": "D",
                        "CPS": _CPS_BY_ADJUSTMENT[adjustment],
                        "Currency": "RMB",
                        "Fill": "Blank",
                    },
                }
                response = self._request(
                    THS_HISTORY_PATH,
                    payload,
                    token_manager=token_manager,
                )
                frames.append(
                    _parse_daily_response(
                        response,
                        adjustment,
                        expected_symbols=frozenset(batch),
                    )
                )
        return pd.concat(frames, ignore_index=True) if frames else _empty_daily_frame()

    def get_realtime_price(
        self,
        *,
        credentials: THSCredentials,
        symbols: Sequence[str],
    ) -> pd.DataFrame:
        canonical_symbols = _canonical_symbols(symbols)
        if not canonical_symbols:
            return _empty_realtime_frame()
        token_manager = THSAccessTokenManager(
            credentials,
            http_client=self._http_client,
            base_url=self._base_url,
        )
        frames: list[pd.DataFrame] = []
        for batch in _batches(canonical_symbols, self._batch_size):
            payload = {
                "codes": ",".join(to_ths_code(symbol) for symbol in batch),
                "indicators": ",".join(THS_REALTIME_INDICATORS),
            }
            response = self._request(
                THS_REALTIME_PATH,
                payload,
                token_manager=token_manager,
            )
            frames.append(
                _parse_realtime_response(
                    response,
                    expected_symbols=frozenset(batch),
                )
            )
        return (
            pd.concat(frames, ignore_index=True)
            if frames
            else _empty_realtime_frame()
        )

    def _request(
        self,
        path: str,
        payload: Mapping[str, Any],
        *,
        token_manager: THSAccessTokenManager,
    ) -> Mapping[str, Any]:
        for attempt in range(2):
            response = self._http_client.post_json(
                f"{self._base_url}{path}",
                headers={
                    "Content-Type": "application/json",
                    "Accept-Encoding": "gzip,deflate",
                    "access_token": token_manager.get_access_token(),
                    "ifindlang": "cn",
                },
                payload=payload,
            )
            error_code = _error_code(response)
            if error_code in THS_TOKEN_ERROR_CODES and attempt == 0:
                if not token_manager.can_refresh:
                    raise ProviderAuthenticationError(
                        f"THS access token failed with error code {error_code}"
                    )
                token_manager.invalidate()
                continue
            if error_code == THS_NO_DATA_ERROR_CODE:
                return {"errorcode": 0, "tables": []}
            if error_code not in (None, 0):
                raise ProviderDataError(
                    f"THS data request failed with error code {error_code}"
                )
            return response
        raise ProviderAuthenticationError("THS access token could not be refreshed")


def to_ths_code(symbol: str) -> str:
    """Convert a canonical Shanghai/Shenzhen ETF code to iFinD notation."""
    value = str(symbol).strip().upper()
    if value.endswith((".SH", ".SZ")):
        code, exchange = value.rsplit(".", 1)
        if len(code) == 6 and code.isdigit() and exchange in {"SH", "SZ"}:
            return value
        raise ValueError(f"invalid THS security code: {symbol}")
    if len(value) != 6 or not value.isdigit():
        raise ValueError(f"invalid ETF symbol: {symbol}")
    if value.startswith("5"):
        return f"{value}.SH"
    if value.startswith("1"):
        return f"{value}.SZ"
    raise ValueError(f"unsupported Shanghai/Shenzhen ETF symbol: {symbol}")


def _canonical_symbols(symbols: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(from_ths_code(to_ths_code(symbol)) for symbol in symbols)
    if len(set(normalized)) != len(normalized):
        raise ValueError("ETF symbols must be unique")
    return normalized


def from_ths_code(code: str) -> str:
    value = str(code).strip().upper()
    if not value.endswith((".SH", ".SZ")):
        raise ProviderDataError("THS response contains an invalid security code")
    symbol = value.rsplit(".", 1)[0]
    if len(symbol) != 6 or not symbol.isdigit():
        raise ProviderDataError("THS response contains an invalid security code")
    return symbol


def _error_code(response: Mapping[str, Any]) -> int | None:
    value = response.get("errorcode")
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ProviderDataError("THS response contains an invalid error code") from exc


def _batches(values: Sequence[str], size: int) -> list[tuple[str, ...]]:
    return [tuple(values[index:index + size]) for index in range(0, len(values), size)]


def _history_date_chunks(
    start_date: date,
    end_date: date,
    *,
    symbol_count: int,
    indicator_count: int,
    max_cells: int,
) -> list[tuple[date, date]]:
    """Conservatively cap each request below the provider's cell limit.

    Calendar days are used instead of estimated trading days so the request
    never relies on a future exchange calendar or underestimates its size.
    """
    if end_date < start_date:
        raise ValueError("end_date cannot precede start_date")
    cells_per_calendar_day = symbol_count * indicator_count
    if cells_per_calendar_day <= 0:
        raise ValueError("history chunk dimensions must be positive")
    days_per_request = max_cells // cells_per_calendar_day
    if days_per_request <= 0:
        raise ValueError("history request cell limit is too small for one day")
    chunks: list[tuple[date, date]] = []
    current = start_date
    while current <= end_date:
        chunk_end = min(
            end_date,
            current + timedelta(days=days_per_request - 1),
        )
        chunks.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return chunks


def _tables(response: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    tables = response.get("tables", [])
    if tables is None:
        return []
    if not isinstance(tables, list) or not all(isinstance(item, Mapping) for item in tables):
        raise ProviderDataError("THS response tables must be a list of objects")
    return tables


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if value is None:
        return []
    return [value]


def _column_values(
    table: Mapping[str, Any], name: str, row_count: int, *, required: bool = True
) -> list[Any]:
    values = _as_list(table.get(name))
    if not values and not required:
        return [None] * row_count
    if len(values) != row_count:
        raise ProviderDataError(
            f"THS response column {name!r} has an inconsistent length"
        )
    return values


def _parse_daily_response(
    response: Mapping[str, Any],
    adjustment: Adjustment,
    *,
    expected_symbols: frozenset[str],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for entry in _tables(response):
        symbol = from_ths_code(str(entry.get("thscode", "")))
        if symbol not in expected_symbols:
            raise ProviderDataError(
                "THS history response contains an unrequested security code"
            )
        table = entry.get("table")
        if not isinstance(table, Mapping):
            raise ProviderDataError("THS history table must be an object")
        times = _as_list(entry.get("time", table.get("time")))
        if not times:
            continue
        row_count = len(times)
        columns = {
            name: _column_values(table, name, row_count)
            for name in ("open", "high", "low", "close", "volume", "amount")
        }
        factors = _column_values(
            table, "ths_af_stock", row_count, required=False
        )
        for index, timestamp in enumerate(times):
            row = {
                "date": timestamp,
                "symbol": symbol,
                "open": columns["open"][index],
                "high": columns["high"][index],
                "low": columns["low"][index],
                "close": columns["close"][index],
                "volume": columns["volume"][index],
                "amount": columns["amount"][index],
                "adjustment": adjustment.value,
                "source": "tonghuashun_ifind_http",
            }
            if factors[index] is not None:
                row["adjust_factor"] = factors[index]
            rows.append(row)
    if not rows:
        return _empty_daily_frame()
    return pd.DataFrame(rows)


def _parse_realtime_response(
    response: Mapping[str, Any], *, expected_symbols: frozenset[str]
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for entry in _tables(response):
        symbol = from_ths_code(str(entry.get("thscode", "")))
        if symbol not in expected_symbols:
            raise ProviderDataError(
                "THS realtime response contains an unrequested security code"
            )
        table = entry.get("table")
        if not isinstance(table, Mapping):
            raise ProviderDataError("THS realtime table must be an object")
        values = {name: _as_list(table.get(name)) for name in THS_REALTIME_INDICATORS}
        row_count = max((len(items) for items in values.values()), default=0)
        if row_count == 0:
            continue
        columns = {
            name: _column_values(table, name, row_count)
            for name in THS_REALTIME_INDICATORS
        }
        response_times = _as_list(entry.get("time"))
        if response_times and len(response_times) != row_count:
            raise ProviderDataError("THS realtime time has an inconsistent length")
        for index in range(row_count):
            timestamp = (
                response_times[index]
                if response_times
                else f"{columns['tradeDate'][index]} {columns['tradeTime'][index]}"
            )
            rows.append(
                {
                    "timestamp": timestamp,
                    "symbol": symbol,
                    "last": columns["latest"][index],
                    "open": columns["open"][index],
                    "high": columns["high"][index],
                    "low": columns["low"][index],
                    "previous_close": columns["preClose"][index],
                    "volume": columns["latestVolume"][index],
                    "amount": columns["latestAmount"][index],
                    "source": "tonghuashun_ifind_http",
                }
            )
    if not rows:
        return _empty_realtime_frame()
    return pd.DataFrame(rows)


def _empty_daily_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "date",
            "symbol",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
            "adjustment",
            "source",
            "adjust_factor",
        ]
    )


def _empty_realtime_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "timestamp",
            "symbol",
            "last",
            "open",
            "high",
            "low",
            "previous_close",
            "volume",
            "amount",
            "source",
        ]
    )
