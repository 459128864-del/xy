#!/usr/bin/env python3
"""Fetch configured real ETF daily data into an ignored local directory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data_pipeline import fetch_universe, write_dataset


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path, default=ROOT / "config/data_sources.yaml"
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    output = args.output or ROOT / config["output"]
    manifest = args.manifest or ROOT / config["manifest"]

    import akshare as ak

    prices, summary = fetch_universe(config, ak.fund_etf_hist_em)
    write_dataset(
        prices,
        summary,
        output_path=output,
        manifest_path=manifest,
        config=config,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
