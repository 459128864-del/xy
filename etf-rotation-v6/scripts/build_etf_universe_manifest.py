#!/usr/bin/env python3
"""Build a frozen ETF universe manifest from an existing local catalogue."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data_provider.universe import write_universe_manifest


def _canonicalize_catalog(
    catalog: pd.DataFrame,
    *,
    source: str,
    source_as_of: str,
) -> pd.DataFrame:
    """Map the current local historical catalogue to the Universe v1 schema."""
    frame = catalog.copy()
    frame = frame.rename(
        columns={"listing_date": "list_date", "delisting_date": "delist_date"}
    )
    required = {"symbol", "name", "list_date", "delist_date"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"catalogue missing columns: {sorted(missing)}")
    if "instrument_id" not in frame:
        frame["instrument_id"] = (
            source
            + ":"
            + frame["symbol"].astype(str).str.strip()
            + ":"
            + frame["list_date"].astype(str).str.strip()
        )
    if "exchange" not in frame:
        frame["exchange"] = "unknown"
    if "category" not in frame:
        frame["category"] = "unknown"
    frame["source"] = source
    frame["source_as_of"] = source_as_of
    return frame


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--catalog",
        type=Path,
        default=ROOT / "data/real/joinquant_etf_catalog.csv",
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=ROOT / "data/real/joinquant_etf_catalog.metadata.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data/metadata/etf_universe_manifest.json",
    )
    args = parser.parse_args()

    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    source = str(metadata["provider_id"])
    source_as_of = str(metadata["complete_through"])
    catalog = pd.read_csv(args.catalog, dtype={"symbol": str})
    universe = _canonicalize_catalog(
        catalog,
        source=source,
        source_as_of=source_as_of,
    )
    manifest = write_universe_manifest(
        universe,
        source=source,
        output_path=args.output,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
