"""Point-in-time ETF universe management without market-data access."""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path

import pandas as pd


UNIVERSE_SCHEMA_VERSION = "1.0.0"
UNIVERSE_COLUMNS = (
    "instrument_id",
    "symbol",
    "name",
    "exchange",
    "list_date",
    "delist_date",
    "category",
    "source",
    "source_as_of",
)


class UniverseValidationError(ValueError):
    """A universe snapshot violates lifecycle or identity invariants."""


def _normalize_date(value: object, *, label: str) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise UniverseValidationError(f"invalid {label}: {value!r}") from exc
    if pd.isna(timestamp):
        raise UniverseValidationError(f"{label} cannot be empty")
    if timestamp.tz is not None:
        raise UniverseValidationError(f"{label} must be timezone-naive")
    return timestamp.normalize()


def validate_universe(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a canonical universe after validating inclusive lifecycles.

    ``list_date`` and ``delist_date`` form an inclusive interval.  An empty
    ``delist_date`` means the instrument remains active.  A symbol may be
    reused by a different instrument only when the two lifecycles do not
    overlap.
    """
    missing = set(UNIVERSE_COLUMNS).difference(frame.columns)
    if missing:
        raise UniverseValidationError(
            f"ETF universe missing columns: {sorted(missing)}"
        )
    output = frame.loc[:, list(UNIVERSE_COLUMNS)].copy()
    if output.empty:
        raise UniverseValidationError("ETF universe cannot be empty")

    string_columns = (
        "instrument_id",
        "symbol",
        "name",
        "exchange",
        "category",
        "source",
        "source_as_of",
    )
    for column in string_columns:
        output[column] = output[column].astype("string").str.strip()
    if output[list(string_columns)].isna().any().any():
        raise UniverseValidationError("ETF universe contains missing required values")
    for column in string_columns:
        if output[column].eq("").any():
            raise UniverseValidationError(f"ETF universe contains blank {column}")

    output["list_date"] = pd.to_datetime(
        output["list_date"], errors="raise"
    ).dt.normalize()
    output["delist_date"] = pd.to_datetime(
        output["delist_date"], errors="coerce"
    ).dt.normalize()
    if output["list_date"].isna().any():
        raise UniverseValidationError("ETF universe contains missing list_date")
    if output["instrument_id"].duplicated().any():
        duplicates = sorted(
            output.loc[output["instrument_id"].duplicated(False), "instrument_id"]
            .astype(str)
            .unique()
        )
        raise UniverseValidationError(f"duplicate instrument_id: {duplicates}")

    reversed_lifecycle = output["delist_date"].notna() & (
        output["list_date"] > output["delist_date"]
    )
    if reversed_lifecycle.any():
        raise UniverseValidationError("list_date cannot be later than delist_date")

    ordered = output.sort_values(
        ["symbol", "list_date", "instrument_id"]
    ).reset_index(drop=True)
    for symbol, rows in ordered.groupby("symbol", sort=False):
        previous_end: pd.Timestamp | None = None
        has_previous = False
        for row in rows.itertuples(index=False):
            if has_previous and (
                previous_end is None or row.list_date <= previous_end
            ):
                raise UniverseValidationError(
                    f"overlapping ETF lifecycle intervals for symbol {symbol}"
                )
            previous_end = None if pd.isna(row.delist_date) else row.delist_date
            has_previous = True
    return ordered


class ETFUniverseProvider(ABC):
    """ETF identity and point-in-time lifecycle boundary only."""

    @abstractmethod
    def get_all_etfs(self) -> pd.DataFrame:
        """Return active and delisted ETF lifecycle records."""

    @abstractmethod
    def get_active_universe(self, on_date: str | date) -> pd.DataFrame:
        """Return ETFs whose inclusive lifecycle contains ``on_date``."""

    @abstractmethod
    def get_etf_metadata(self, symbol: str) -> pd.DataFrame:
        """Return every non-overlapping lifecycle recorded for ``symbol``."""

    @abstractmethod
    def is_available(self, symbol: str, on_date: str | date) -> bool:
        """Return whether ``symbol`` may enter the universe on ``on_date``."""


class DataFrameETFUniverseProvider(ETFUniverseProvider):
    """Deterministic in-memory provider used by CSV and future API adapters."""

    def __init__(self, universe: pd.DataFrame) -> None:
        self._universe = validate_universe(universe)

    def get_all_etfs(self) -> pd.DataFrame:
        return self._universe.copy()

    def get_active_universe(self, on_date: str | date) -> pd.DataFrame:
        timestamp = _normalize_date(on_date, label="universe date")
        active = self._universe["list_date"].le(timestamp) & (
            self._universe["delist_date"].isna()
            | self._universe["delist_date"].ge(timestamp)
        )
        return self._universe.loc[active].reset_index(drop=True).copy()

    def get_etf_metadata(self, symbol: str) -> pd.DataFrame:
        normalized = str(symbol).strip()
        return self._universe.loc[
            self._universe["symbol"].eq(normalized)
        ].reset_index(drop=True).copy()

    def is_available(self, symbol: str, on_date: str | date) -> bool:
        timestamp = _normalize_date(on_date, label="universe date")
        records = self._universe["symbol"].eq(str(symbol).strip())
        active = self._universe["list_date"].le(timestamp) & (
            self._universe["delist_date"].isna()
            | self._universe["delist_date"].ge(timestamp)
        )
        return bool((records & active).any())


class CSVETFUniverseProvider(DataFrameETFUniverseProvider):
    """Load a frozen local universe without any network or price access."""

    def __init__(self, path: Path) -> None:
        frame = pd.read_csv(path, dtype="string")
        super().__init__(frame)


def _canonical_universe_bytes(universe: pd.DataFrame) -> bytes:
    normalized = validate_universe(universe)
    serialized = normalized.copy()
    serialized["list_date"] = serialized["list_date"].dt.strftime("%Y-%m-%d")
    serialized["delist_date"] = serialized["delist_date"].dt.strftime("%Y-%m-%d")
    return serialized.to_csv(
        index=False,
        lineterminator="\n",
        na_rep="",
    ).encode("utf-8")


def build_universe_manifest(
    universe: pd.DataFrame,
    *,
    source: str,
    schema_version: str = UNIVERSE_SCHEMA_VERSION,
) -> dict[str, object]:
    """Build a content-addressed, reproducible universe manifest.

    ``generated_at`` is derived from the frozen input's ``source_as_of`` rather
    than the wall clock.  Consequently the same snapshot always produces the
    same manifest, even when rows arrive in a different order.
    """
    normalized = validate_universe(universe)
    normalized_source = str(source).strip()
    normalized_schema = str(schema_version).strip()
    if not normalized_source:
        raise UniverseValidationError("manifest source cannot be blank")
    if not normalized_schema:
        raise UniverseValidationError("schema_version cannot be blank")

    source_dates = pd.to_datetime(
        normalized["source_as_of"], errors="raise", utc=True
    )
    generated_at = source_dates.max().isoformat().replace("+00:00", "Z")
    content = _canonical_universe_bytes(normalized)
    identity = (
        f"schema_version={normalized_schema}\nsource={normalized_source}\n".encode(
            "utf-8"
        )
        + content
    )
    universe_version = "sha256:" + hashlib.sha256(identity).hexdigest()
    return {
        "generated_at": generated_at,
        "source": normalized_source,
        "universe_version": universe_version,
        "instrument_count": int(normalized["instrument_id"].nunique()),
        "schema_version": normalized_schema,
    }


def write_universe_manifest(
    universe: pd.DataFrame,
    *,
    source: str,
    output_path: Path,
    schema_version: str = UNIVERSE_SCHEMA_VERSION,
) -> dict[str, object]:
    """Write the deterministic manifest and return its exact content."""
    manifest = build_universe_manifest(
        universe,
        source=source,
        schema_version=schema_version,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest
