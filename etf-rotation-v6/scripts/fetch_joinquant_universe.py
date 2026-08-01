#!/usr/bin/env python3
"""Fetch an all-history ETF lifecycle catalogue without exposing credentials."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.joinquant_universe import (  # noqa: E402
    build_joinquant_metadata, fetch_joinquant_etf_catalog,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data/real/joinquant_etf_catalog.csv",
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=ROOT / "data/real/joinquant_etf_catalog.metadata.json",
    )
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()

    username = os.environ.get("JQDATA_USERNAME")
    password = os.environ.get("JQDATA_PASSWORD")
    if not username or not password:
        parser.error("JQDATA_USERNAME and JQDATA_PASSWORD must be set")

    try:
        import jqdatasdk
    except ImportError as error:
        raise SystemExit("jqdatasdk is not installed; install requirements.txt") from error

    jqdatasdk.auth(username, password)
    catalog = fetch_joinquant_etf_catalog(jqdatasdk.get_all_securities)
    metadata = build_joinquant_metadata(catalog, as_of=args.as_of)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.metadata.parent.mkdir(parents=True, exist_ok=True)
    catalog.to_csv(args.output, index=False)
    args.metadata.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "catalog": str(args.output),
        "metadata": str(args.metadata),
        "symbols": len(catalog),
        "delisted_symbols": int(catalog["delisting_date"].notna().sum()),
        "complete_through": args.as_of.isoformat(),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
