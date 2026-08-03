"""Provider-independent ETF price-data contract for V6."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import Enum

import pandas as pd

from .schemas import to_backtest_prices


class Adjustment(str, Enum):
    """Canonical adjustment request; provider-specific values are adapters' job."""

    NONE = "none"
    FORWARD = "qfq"
    BACKWARD = "hfq"


@dataclass(frozen=True)
class ProviderCapabilities:
    daily_price: bool
    realtime_price: bool
    volume: bool
    amount: bool
    adjusted_price: bool


class PriceProvider(ABC):
    """Price-only boundary between API vendors and local data preparation."""

    provider_id: str

    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """Declare supported operations without making an API request."""

    @abstractmethod
    def get_daily_price(
        self,
        symbols: Sequence[str],
        *,
        start_date: date,
        end_date: date,
        adjustment: Adjustment = Adjustment.FORWARD,
    ) -> pd.DataFrame:
        """Return canonical daily OHLCV, amount, and adjustment evidence."""

    @abstractmethod
    def get_realtime_price(self, symbols: Sequence[str]) -> pd.DataFrame:
        """Return canonical realtime quotes; implementations may reserve it."""

    @staticmethod
    def as_backtest_prices(daily_prices: pd.DataFrame) -> pd.DataFrame:
        """Convert any provider result to the existing V6 backtest input."""
        return to_backtest_prices(daily_prices)


# Compatibility name for callers that already use ``DataProvider``.  The
# contract is price-only; Universe operations live exclusively in
# ``ETFUniverseProvider``.
DataProvider = PriceProvider
