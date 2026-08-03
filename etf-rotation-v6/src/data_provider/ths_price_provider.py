"""Offline THS price-provider boundary; no Universe operations are exposed."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Protocol

import pandas as pd

from .base import Adjustment, PriceProvider, ProviderCapabilities
from .exceptions import ProviderNotConnectedError
from .schemas import validate_daily_prices, validate_realtime_prices
from .ths_auth import THSCredentials
from .ths_http_transport import THSHTTPPriceTransport


class THSPriceTransport(Protocol):
    """Transport contract limited to historical and realtime price data."""

    def get_daily_price(
        self,
        *,
        credentials: THSCredentials,
        symbols: Sequence[str],
        start_date: date,
        end_date: date,
        adjustment: Adjustment,
    ) -> pd.DataFrame: ...

    def get_realtime_price(
        self, *, credentials: THSCredentials, symbols: Sequence[str]
    ) -> pd.DataFrame: ...


class THSPriceProvider(PriceProvider):
    """THS adapter for OHLCV, amount, adjustment, and realtime quotes only."""

    provider_id = "tonghuashun"

    def __init__(
        self,
        credentials: THSCredentials,
        *,
        transport: THSPriceTransport | None = None,
    ) -> None:
        self._credentials = credentials
        self._transport = transport

    @classmethod
    def from_environment(
        cls,
        *,
        environment: Mapping[str, str] | None = None,
        transport: THSPriceTransport | None = None,
    ) -> "THSPriceProvider":
        return cls(
            THSCredentials.from_environment(environment),
            transport=transport or THSHTTPPriceTransport(),
        )

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            daily_price=True,
            realtime_price=True,
            volume=True,
            amount=True,
            adjusted_price=True,
        )

    def _require_transport(self) -> THSPriceTransport:
        if self._transport is None:
            raise ProviderNotConnectedError(
                "THS price transport is not implemented; no network request was made"
            )
        return self._transport

    def get_daily_price(
        self,
        symbols: Sequence[str],
        *,
        start_date: date,
        end_date: date,
        adjustment: Adjustment = Adjustment.FORWARD,
    ) -> pd.DataFrame:
        if end_date < start_date:
            raise ValueError("end_date cannot precede start_date")
        frame = self._require_transport().get_daily_price(
            credentials=self._credentials,
            symbols=tuple(symbols),
            start_date=start_date,
            end_date=end_date,
            adjustment=adjustment,
        )
        return validate_daily_prices(frame)

    def get_realtime_price(self, symbols: Sequence[str]) -> pd.DataFrame:
        frame = self._require_transport().get_realtime_price(
            credentials=self._credentials,
            symbols=tuple(symbols),
        )
        return validate_realtime_prices(frame)
