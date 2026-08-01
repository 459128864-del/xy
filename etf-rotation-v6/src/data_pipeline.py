"""Real ETF data normalization and quality gates."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd


REQUIRED_PRICE_COLUMNS = ["date", "symbol", "close"]
REQUIRED_UNIVERSE_COLUMNS = [
    "symbol", "name", "listing_date", "delisting_date", "source"
]


def load_historical_universe(path: Path) -> pd.DataFrame:
    """Load a point-in-time ETF catalogue supplied by an authoritative source.

    ``delisting_date`` is optional for active funds.  The loader deliberately
    does not infer lifecycle dates from the first/last available price because
    doing so would confuse missing observations with listing events.
    """
    catalog = pd.read_csv(path, dtype={"symbol": str})
    missing = set(REQUIRED_UNIVERSE_COLUMNS).difference(catalog.columns)
    if missing:
        raise ValueError(f"historical universe missing columns: {sorted(missing)}")
    catalog = catalog.loc[:, REQUIRED_UNIVERSE_COLUMNS].copy()
    if catalog[["symbol", "name", "listing_date", "source"]].isna().any().any():
        raise ValueError("historical universe contains missing required values")
    catalog["symbol"] = catalog["symbol"].str.strip()
    catalog["name"] = catalog["name"].astype(str).str.strip()
    catalog["source"] = catalog["source"].astype(str).str.strip()
    catalog["listing_date"] = pd.to_datetime(
        catalog["listing_date"], errors="raise"
    ).dt.normalize()
    catalog["delisting_date"] = pd.to_datetime(
        catalog["delisting_date"], errors="coerce"
    ).dt.normalize()
    if catalog.empty:
        raise ValueError("historical universe is empty")
    if catalog[["symbol", "name", "listing_date", "source"]].isna().any().any():
        raise ValueError("historical universe contains missing required values")
    if catalog["symbol"].eq("").any() or catalog["source"].eq("").any():
        raise ValueError("historical universe contains blank symbol or source")
    if catalog["symbol"].duplicated().any():
        raise ValueError("historical universe contains duplicate symbols")
    invalid_lifecycle = catalog["delisting_date"].notna() & (
        catalog["delisting_date"] < catalog["listing_date"]
    )
    if invalid_lifecycle.any():
        raise ValueError("delisting_date cannot precede listing_date")
    return catalog.sort_values("symbol").reset_index(drop=True)


def point_in_time_universe(catalog: pd.DataFrame, date: object) -> set[str]:
    """Return symbols listed on a date using [listing, delisting) semantics."""
    timestamp = pd.Timestamp(date).normalize()
    eligible = catalog["listing_date"].le(timestamp) & (
        catalog["delisting_date"].isna()
        | catalog["delisting_date"].gt(timestamp)
    )
    return set(catalog.loc[eligible, "symbol"].astype(str))


def validate_historical_coverage(
    prices: pd.DataFrame,
    catalog: pd.DataFrame,
    *,
    start_date: object,
    end_date: object,
) -> dict[str, object]:
    """Prove that every lifecycle-overlapping ETF has price observations.

    This is a strict claim gate, not a missing-data filler.  It includes
    delisted products and rejects price rows outside the recorded lifecycle.
    """
    validate_price_data(prices)
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    if end < start:
        raise ValueError("end_date cannot precede start_date")
    overlaps = catalog["listing_date"].le(end) & (
        catalog["delisting_date"].isna()
        | catalog["delisting_date"].gt(start)
    )
    expected = set(catalog.loc[overlaps, "symbol"].astype(str))
    observed = set(prices["symbol"].astype(str))
    missing = sorted(expected - observed)
    unexpected = sorted(observed - expected)
    if missing:
        raise ValueError(f"historical price coverage missing symbols: {missing}")
    if unexpected:
        raise ValueError(f"price data contains symbols outside lifecycle: {unexpected}")

    lifecycle = catalog.set_index("symbol")
    merged = prices.loc[:, ["date", "symbol"]].copy()
    merged["date"] = pd.to_datetime(merged["date"]).dt.normalize()
    merged = merged.join(lifecycle[["listing_date", "delisting_date"]], on="symbol")
    outside = merged["date"].lt(merged["listing_date"]) | (
        merged["delisting_date"].notna()
        & merged["date"].ge(merged["delisting_date"])
    )
    if outside.any():
        raise ValueError("price observations fall outside ETF lifecycle")
    return {
        "catalog_symbols": int(len(catalog)),
        "eligible_symbols": int(len(expected)),
        "delisted_symbols": int(catalog["delisting_date"].notna().sum()),
        "observed_symbols": int(len(observed)),
        "start_date": start.date().isoformat(),
        "end_date": end.date().isoformat(),
    }


def normalize_akshare_etf(
    raw: pd.DataFrame,
    *,
    symbol: str,
    name: str,
    category: str,
    adjustment: str,
) -> pd.DataFrame:
    """Normalize one fund_etf_hist_em response without filling missing dates."""
    required = {"日期", "收盘"}
    missing = required.difference(raw.columns)
    if missing:
        raise ValueError(f"provider response missing columns: {sorted(missing)}")
    frame = raw.loc[:, ["日期", "收盘"]].rename(
        columns={"日期": "date", "收盘": "close"}
    )
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    frame["close"] = pd.to_numeric(frame["close"], errors="raise")
    frame["symbol"] = str(symbol)
    frame["name"] = name
    frame["category"] = category
    frame["source"] = "akshare:fund_etf_hist_em/eastmoney"
    frame["adjustment"] = adjustment
    return frame.sort_values("date").reset_index(drop=True)


def validate_price_data(prices: pd.DataFrame) -> dict[str, object]:
    """Validate long-form ETF data and return a deterministic summary."""
    missing = set(REQUIRED_PRICE_COLUMNS).difference(prices.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    if prices.empty:
        raise ValueError("price data is empty")
    if prices[REQUIRED_PRICE_COLUMNS].isna().any().any():
        raise ValueError("required price fields contain missing values")
    if prices.duplicated(["date", "symbol"]).any():
        raise ValueError("duplicate date-symbol observations")
    if prices["close"].le(0.0).any():
        raise ValueError("close prices must be positive")

    ordered = prices.sort_values(["symbol", "date"])
    if not ordered.index.equals(prices.index):
        raise ValueError("price data must be sorted by symbol and date")

    per_symbol = []
    for symbol, group in prices.groupby("symbol", sort=True):
        per_symbol.append({
            "symbol": str(symbol),
            "rows": int(len(group)),
            "start_date": group["date"].min().date().isoformat(),
            "end_date": group["date"].max().date().isoformat(),
        })
    return {
        "rows": int(len(prices)),
        "symbols": int(prices["symbol"].nunique()),
        "start_date": prices["date"].min().date().isoformat(),
        "end_date": prices["date"].max().date().isoformat(),
        "per_symbol": per_symbol,
    }


def fetch_universe(
    config: dict,
    fetcher: Callable[..., pd.DataFrame],
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Fetch, normalize, validate, and describe a configured ETF universe."""
    frames = []
    for item in config["universe"]:
        raw = fetcher(
            symbol=str(item["symbol"]),
            period=config["period"],
            start_date=str(config["start_date"]),
            end_date=str(config["end_date"]),
            adjust=config["adjust"],
        )
        frames.append(normalize_akshare_etf(
            raw,
            symbol=str(item["symbol"]),
            name=item["name"],
            category=item["category"],
            adjustment=config["adjust"],
        ))
    prices = pd.concat(frames, ignore_index=True).sort_values(
        ["symbol", "date"]
    ).reset_index(drop=True)
    summary = validate_price_data(prices)
    return prices, summary


def normalize_akshare_index(raw: pd.DataFrame, *, symbol: str) -> pd.DataFrame:
    """Normalize an AKShare daily-index response for benchmark comparison."""
    required = {"date", "close"}
    missing = required.difference(raw.columns)
    if missing:
        raise ValueError(f"provider response missing columns: {sorted(missing)}")
    frame = raw.loc[:, ["date", "close"]].copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    frame["close"] = pd.to_numeric(frame["close"], errors="raise")
    frame["symbol"] = str(symbol)
    frame = frame.sort_values("date").reset_index(drop=True)
    validate_price_data(frame)
    return frame


def write_dataset(
    prices: pd.DataFrame,
    summary: dict[str, object],
    *,
    output_path: Path,
    manifest_path: Path,
    config: dict,
    historical_catalog: pd.DataFrame | None = None,
    catalog_metadata: dict[str, object] | None = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    prices.to_csv(output_path, index=False)
    digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
    coverage = None
    catalog_digest = None
    controlled = False
    if historical_catalog is not None:
        if not catalog_metadata:
            raise ValueError("historical catalog metadata is required")
        required_metadata = {
            "source_name", "source_url", "authoritative", "scope",
            "complete_through", "expected_symbol_count",
        }
        missing_metadata = required_metadata.difference(catalog_metadata)
        if missing_metadata:
            raise ValueError(
                f"historical catalog metadata missing fields: {sorted(missing_metadata)}"
            )
        if catalog_metadata.get("scope") != "all_sh_sz_etfs":
            raise ValueError("historical catalog scope must be all_sh_sz_etfs")
        if not catalog_metadata.get("authoritative"):
            raise ValueError("historical catalog source must be authoritative")
        complete_through = pd.Timestamp(
            catalog_metadata.get("complete_through")
        ).normalize()
        if pd.isna(complete_through):
            raise ValueError("historical catalog complete_through is invalid")
        requested_end = pd.Timestamp(str(config["end_date"])).normalize()
        if complete_through < requested_end:
            raise ValueError("historical catalog does not cover requested end date")
        coverage = validate_historical_coverage(
            prices,
            historical_catalog,
            start_date=str(config["start_date"]),
            end_date=str(config["end_date"]),
        )
        if int(catalog_metadata["expected_symbol_count"]) != len(historical_catalog):
            raise ValueError("historical catalog symbol count does not match metadata")
        if coverage["delisted_symbols"] <= 0:
            raise ValueError("complete historical catalog must include delisted ETFs")
        catalog_bytes = historical_catalog.to_csv(index=False).encode("utf-8")
        catalog_digest = hashlib.sha256(catalog_bytes).hexdigest()
        controlled = True
    elif config.get("survivorship_bias_controlled"):
        raise ValueError(
            "cannot claim survivorship control without a validated historical catalog"
        )

    manifest = {
        "provider": config["provider"],
        "interface": config["interface"],
        "period": config["period"],
        "adjustment": config["adjust"],
        "requested_start_date": str(config["start_date"]),
        "requested_end_date": str(config["end_date"]),
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "sha256": digest,
        "universe_scope": config.get("universe_scope", "unspecified"),
        "historical_universe_complete": controlled,
        "survivorship_bias_controlled": controlled,
        "historical_catalog_sha256": catalog_digest,
        "historical_catalog_metadata": catalog_metadata,
        "historical_coverage": coverage,
        "summary": summary,
        "notes": [
            "No pre-listing rows are synthesized.",
            "No missing trading dates are forward-filled.",
            (
                "Point-in-time lifecycle coverage was validated."
                if controlled else
                "A complete authoritative historical ETF catalogue was not supplied."
            ),
        ],
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def require_survivorship_controlled(manifest: dict[str, object]) -> None:
    """Prevent a fixed/current universe from being presented as bias-controlled."""
    coverage = manifest.get("historical_coverage")
    metadata = manifest.get("historical_catalog_metadata")
    valid_evidence = (
        isinstance(coverage, dict)
        and coverage.get("eligible_symbols") == coverage.get("observed_symbols")
        and isinstance(metadata, dict)
        and metadata.get("scope") == "all_sh_sz_etfs"
        and metadata.get("authoritative") is True
        and bool(metadata.get("source_name"))
        and bool(metadata.get("source_url"))
        and bool(metadata.get("complete_through"))
        and metadata.get("expected_symbol_count") == coverage.get("catalog_symbols")
        and coverage.get("delisted_symbols", 0) > 0
        and bool(manifest.get("historical_catalog_sha256"))
    )
    if (
        not manifest.get("historical_universe_complete")
        or not manifest.get("survivorship_bias_controlled")
        or not valid_evidence
    ):
        raise ValueError(
            "historical universe is incomplete; survivorship-bias-controlled claims are prohibited"
        )
