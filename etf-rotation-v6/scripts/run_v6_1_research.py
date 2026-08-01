#!/usr/bin/env python3
"""Run the locked-holdout, single-factor V6.1 research protocol."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.optimization import run_single_factor_research


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--strategy-config", type=Path, default=ROOT / "config/strategy_v6.yaml")
    parser.add_argument("--research-config", type=Path, default=ROOT / "config/v6_1_research.yaml")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prices = pd.read_csv(args.data, parse_dates=["date"])
    base = yaml.safe_load(args.strategy_config.read_text(encoding="utf-8"))
    research = yaml.safe_load(args.research_config.read_text(encoding="utf-8"))["research"]
    result = run_single_factor_research(prices, base, research)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
