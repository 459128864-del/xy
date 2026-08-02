#!/usr/bin/env python3
"""Fetch V6 prices through JQData and validate the historical ETF catalogue."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data_pipeline import (  # noqa: E402
    build_fetch_config, fetch_universe, load_historical_universe,
    normalize_akshare_index, write_dataset,
)
from src.joinquant_universe import (  # noqa: E402
    build_joinquant_price_fetcher,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "config/data_sources.yaml")
    parser.add_argument(
        "--catalog", type=Path,
        default=ROOT / "data/real/joinquant_etf_catalog.csv",
    )
    parser.add_argument(
        "--catalog-metadata", type=Path,
        default=ROOT / "data/real/joinquant_etf_catalog.metadata.json",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--benchmark-output", type=Path)
    args = parser.parse_args()

    username = os.environ.get("JQDATA_USERNAME")
    password = os.environ.get("JQDATA_PASSWORD")
    if not username or not password:
        parser.error("JQDATA_USERNAME and JQDATA_PASSWORD must be set")
    import jqdatasdk
    jqdatasdk.auth(username, password)

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    catalog = load_historical_universe(args.catalog)
    metadata = json.loads(args.catalog_metadata.read_text(encoding="utf-8"))
    fetch_config = build_fetch_config(config, catalog)
    fetch_config["provider"] = "joinquant"
    fetch_config["interface"] = "get_price"
    fetcher = build_joinquant_price_fetcher(jqdatasdk.get_price)
    prices, summary = fetch_universe(fetch_config, fetcher)

    manifest_config = dict(fetch_config)
    output = args.output or ROOT / config["output"]
    manifest = args.manifest or ROOT / config["manifest"]
    write_dataset(
        prices, summary, output_path=output, manifest_path=manifest,
        config=manifest_config, historical_catalog=catalog,
        catalog_metadata=metadata,
    )
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))

    benchmark_cfg = config["benchmark"]
    benchmark_raw = jqdatasdk.get_price(
        "000300.XSHG",
        start_date=pd.Timestamp(str(config["start_date"])).date(),
        end_date=pd.Timestamp(str(config["end_date"])).date(),
        frequency="daily", fields=["close"], skip_paused=True, fq="pre",
    )
    benchmark_frame = benchmark_raw.loc[:, ["close"]].reset_index()
    benchmark_frame = benchmark_frame.rename(
        columns={benchmark_frame.columns[0]: "date"}
    )
    benchmark = normalize_akshare_index(
        benchmark_frame, symbol=benchmark_cfg["symbol"]
    )
    benchmark_output = args.benchmark_output or ROOT / benchmark_cfg["output"]
    benchmark_output.parent.mkdir(parents=True, exist_ok=True)
    benchmark.to_csv(benchmark_output, index=False)
    print(json.dumps({
        "etf": summary,
        "benchmark_rows": len(benchmark),
        "catalog_validation_mode": manifest_payload["catalog_validation_mode"],
        "survivorship_bias_controlled": manifest_payload["survivorship_bias_controlled"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
