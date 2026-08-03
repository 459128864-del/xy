"""Switchable ETF market-data providers for the V6 research data layer."""

from .base import Adjustment, DataProvider, PriceProvider, ProviderCapabilities
from .exceptions import (
    DataProviderError,
    ProviderAuthenticationError,
    ProviderDataError,
    ProviderNotConnectedError,
    UnsupportedDataProviderError,
)
from .factory import (
    create_data_provider,
    create_price_provider,
    register_data_provider,
    register_price_provider,
)
from .schemas import (
    DAILY_PRICE_COLUMNS,
    DAILY_PRICE_OPTIONAL_COLUMNS,
    REALTIME_PRICE_COLUMNS,
    to_backtest_prices,
)
from .ths_auth import THSCredentials
from .ths_price_provider import THSPriceProvider, THSPriceTransport
from .ths_universe_provider import THSETFUniverseProvider, THSUniverseTransport
from .universe import (
    UNIVERSE_COLUMNS,
    UNIVERSE_SCHEMA_VERSION,
    CSVETFUniverseProvider,
    DataFrameETFUniverseProvider,
    ETFUniverseProvider,
    UniverseValidationError,
    build_universe_manifest,
    validate_universe,
    write_universe_manifest,
)

__all__ = [
    "Adjustment",
    "CSVETFUniverseProvider",
    "DAILY_PRICE_COLUMNS",
    "DAILY_PRICE_OPTIONAL_COLUMNS",
    "DataProvider",
    "DataProviderError",
    "DataFrameETFUniverseProvider",
    "ETFUniverseProvider",
    "PriceProvider",
    "ProviderAuthenticationError",
    "ProviderCapabilities",
    "ProviderDataError",
    "ProviderNotConnectedError",
    "REALTIME_PRICE_COLUMNS",
    "THSCredentials",
    "THSETFUniverseProvider",
    "THSPriceProvider",
    "THSPriceTransport",
    "THSUniverseTransport",
    "UNIVERSE_COLUMNS",
    "UNIVERSE_SCHEMA_VERSION",
    "UnsupportedDataProviderError",
    "UniverseValidationError",
    "build_universe_manifest",
    "create_data_provider",
    "create_price_provider",
    "register_data_provider",
    "register_price_provider",
    "to_backtest_prices",
    "validate_universe",
    "write_universe_manifest",
]
