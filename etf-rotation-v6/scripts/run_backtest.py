#!/usr/bin/env python3
"""Run the V6 backtest and persist machine-readable results."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.backtest import run_backtest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=ROOT / "data/sample/etf_sample.csv")
    parser.add_argument("--config", type=Path, default=ROOT / "config/strategy_v6.yaml")
    parser.add_argument("--output", type=Path, default=ROOT / "backtests")
    args = parser.parse_args()

    prices = pd.read_csv(args.data, parse_dates=["date"])
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    result = run_backtest(prices, config)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "baseline_metrics.json").write_text(
        json.dumps(result["metrics"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    result["equity_curve"].to_csv(args.output / "equity_curve.csv", index=False)
    result["execution_events"].to_csv(args.output / "execution_events.csv", index=False)
    print(json.dumps(result["metrics"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
