"""Real ETF data normalization and quality gates."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd


REQUIRED_PRICE_COLUMNS = ["date", "symbol", "close"]


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
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    prices.to_csv(output_path, index=False)
    digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
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
        "historical_universe_complete": bool(
            config.get("historical_universe_complete", False)
        ),
        "survivorship_bias_controlled": bool(
            config.get("survivorship_bias_controlled", False)
        ),
        "summary": summary,
        "notes": [
            "No pre-listing rows are synthesized.",
            "No missing trading dates are forward-filled.",
            "Delisting and historical-universe rules remain to be confirmed.",
        ],
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def require_survivorship_controlled(manifest: dict[str, object]) -> None:
    """Prevent a fixed/current universe from being presented as bias-controlled."""
    if not manifest.get("historical_universe_complete") or not manifest.get(
        "survivorship_bias_controlled"
    ):
        raise ValueError(
            "historical universe is incomplete; survivorship-bias-controlled claims are prohibited"
        )
