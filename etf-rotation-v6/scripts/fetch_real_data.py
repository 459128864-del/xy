#!/usr/bin/env python3
"""Fetch configured real ETF daily data into an ignored local directory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data_pipeline import fetch_universe, normalize_akshare_index, write_dataset


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path, default=ROOT / "config/data_sources.yaml"
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--benchmark-output", type=Path)
    parser.add_argument("--benchmark-only", action="store_true")
    args = parser.parse_args()

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    output = args.output or ROOT / config["output"]
    manifest = args.manifest or ROOT / config["manifest"]

    import akshare as ak

    summary = None
    if not args.benchmark_only:
        prices, summary = fetch_universe(config, ak.fund_etf_hist_em)
        write_dataset(
            prices,
            summary,
            output_path=output,
            manifest_path=manifest,
            config=config,
        )
    benchmark_cfg = config["benchmark"]
    benchmark_raw = ak.stock_zh_index_daily(symbol=benchmark_cfg["symbol"])
    benchmark_raw["date"] = pd.to_datetime(benchmark_raw["date"])
    start = pd.to_datetime(str(config["start_date"]))
    end = pd.to_datetime(str(config["end_date"]))
    benchmark_raw = benchmark_raw.loc[benchmark_raw["date"].between(start, end)]
    benchmark = normalize_akshare_index(
        benchmark_raw, symbol=benchmark_cfg["symbol"]
    )
    benchmark_output = args.benchmark_output or ROOT / benchmark_cfg["output"]
    benchmark_output.parent.mkdir(parents=True, exist_ok=True)
    benchmark.to_csv(benchmark_output, index=False)
    print(json.dumps({"etf": summary, "benchmark_rows": len(benchmark)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
