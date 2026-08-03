"""Canonical ETF market-data schemas shared by every provider adapter."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from .exceptions import ProviderDataError


DAILY_PRICE_COLUMNS = (
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
)

# Optional fields preserve the raw price and the provider's adjustment evidence.
DAILY_PRICE_OPTIONAL_COLUMNS = (
    "raw_open",
    "raw_high",
    "raw_low",
    "raw_close",
    "adjust_factor",
    "name",
    "category",
)

REALTIME_PRICE_COLUMNS = (
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
)


def _require_columns(frame: pd.DataFrame, required: Iterable[str], label: str) -> None:
    missing = set(required).difference(frame.columns)
    if missing:
        raise ProviderDataError(f"{label} missing canonical columns: {sorted(missing)}")


def validate_daily_prices(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate daily OHLCV/amount data without filling missing observations.

    ``open/high/low/close`` are the selected price series for the requested
    adjustment mode.  If available, unadjusted prices and ``adjust_factor``
    remain in the optional fields for auditability.
    """
    _require_columns(frame, DAILY_PRICE_COLUMNS, "daily price")
    output = frame.copy()
    if output.empty:
        return output
    output["date"] = pd.to_datetime(output["date"], errors="raise").dt.normalize()
    output["symbol"] = output["symbol"].astype(str).str.strip()
    numeric = ["open", "high", "low", "close", "volume", "amount"]
    for column in numeric:
        output[column] = pd.to_numeric(output[column], errors="raise")
    if output[list(DAILY_PRICE_COLUMNS)].isna().any().any():
        raise ProviderDataError("daily price contains missing required values")
    if output["symbol"].eq("").any():
        raise ProviderDataError("daily price contains blank symbols")
    if output.duplicated(["date", "symbol"]).any():
        raise ProviderDataError("daily price contains duplicate date-symbol rows")
    if output[["open", "high", "low", "close"]].le(0.0).any().any():
        raise ProviderDataError("daily OHLC prices must be positive")
    if output[["volume", "amount"]].lt(0.0).any().any():
        raise ProviderDataError("daily volume and amount cannot be negative")
    return output.sort_values(["symbol", "date"]).reset_index(drop=True)


def validate_realtime_prices(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate the reserved realtime quote contract."""
    _require_columns(frame, REALTIME_PRICE_COLUMNS, "realtime price")
    output = frame.copy()
    if output.empty:
        return output
    output["timestamp"] = pd.to_datetime(output["timestamp"], errors="raise")
    output["symbol"] = output["symbol"].astype(str).str.strip()
    if output[list(REALTIME_PRICE_COLUMNS)].isna().any().any():
        raise ProviderDataError("realtime price contains missing required values")
    if output.duplicated(["timestamp", "symbol"]).any():
        raise ProviderDataError("realtime price contains duplicate timestamp-symbol rows")
    return output.sort_values(["symbol", "timestamp"]).reset_index(drop=True)


def to_backtest_prices(frame: pd.DataFrame) -> pd.DataFrame:
    """Project canonical daily data to the unchanged V6 backtest input."""
    validated = validate_daily_prices(frame)
    columns = ["date", "symbol", "close"]
    columns.extend(
        column for column in ("name", "category", "source", "adjustment")
        if column in validated.columns
    )
    return validated.loc[:, columns].copy()
