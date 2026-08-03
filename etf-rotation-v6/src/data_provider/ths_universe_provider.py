"""Offline THS ETF-Universe boundary; no price operations are exposed."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Protocol

import pandas as pd

from .exceptions import ProviderNotConnectedError
from .ths_auth import THSCredentials
from .universe import (
    DataFrameETFUniverseProvider,
    ETFUniverseProvider,
    validate_universe,
)


class THSUniverseTransport(Protocol):
    """Future official ETF-list transport, separate from price transport."""

    def get_all_etfs(self, *, credentials: THSCredentials) -> pd.DataFrame: ...


class THSETFUniverseProvider(ETFUniverseProvider):
    """THS adapter for ETF identity, lifecycle, and classification only."""

    provider_id = "tonghuashun"

    def __init__(
        self,
        credentials: THSCredentials,
        *,
        transport: THSUniverseTransport | None = None,
    ) -> None:
        self._credentials = credentials
        self._transport = transport
        self._delegate: DataFrameETFUniverseProvider | None = None

    @classmethod
    def from_environment(
        cls,
        *,
        environment: Mapping[str, str] | None = None,
        transport: THSUniverseTransport | None = None,
    ) -> "THSETFUniverseProvider":
        return cls(
            THSCredentials.from_environment(environment),
            transport=transport,
        )

    def _universe(self) -> DataFrameETFUniverseProvider:
        if self._delegate is None:
            if self._transport is None:
                raise ProviderNotConnectedError(
                    "THS Universe transport is not implemented; no network request was made"
                )
            frame = validate_universe(
                self._transport.get_all_etfs(credentials=self._credentials)
            )
            self._delegate = DataFrameETFUniverseProvider(frame)
        return self._delegate

    def get_all_etfs(self) -> pd.DataFrame:
        return self._universe().get_all_etfs()

    def get_active_universe(self, on_date: str | date) -> pd.DataFrame:
        return self._universe().get_active_universe(on_date)

    def get_etf_metadata(self, symbol: str) -> pd.DataFrame:
        return self._universe().get_etf_metadata(symbol)

    def is_available(self, symbol: str, on_date: str | date) -> bool:
        return self._universe().is_available(symbol, on_date)
