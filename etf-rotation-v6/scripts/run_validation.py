#!/usr/bin/env python3
"""Run fixed-parameter rolling, expanding, and regime validation."""

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
from src.validation import build_annual_windows, regime_metrics, run_window_validation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--strategy-config", type=Path, default=ROOT / "config/strategy_v6.yaml")
    parser.add_argument("--validation-config", type=Path, default=ROOT / "config/validation_v6.yaml")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prices = pd.read_csv(args.data, parse_dates=["date"])
    benchmark = pd.read_csv(args.benchmark, parse_dates=["date"])
    strategy = yaml.safe_load(args.strategy_config.read_text(encoding="utf-8"))
    validation = yaml.safe_load(args.validation_config.read_text(encoding="utf-8"))
    method = validation["methodology"]
    dates = prices["date"].drop_duplicates()
    rolling = build_annual_windows(
        dates, train_years=method["rolling_train_years"],
        test_years=method["test_years"], step_years=method["step_years"],
    )
    expanding = build_annual_windows(
        dates, train_years=method["rolling_train_years"],
        test_years=method["test_years"], step_years=method["step_years"], expanding=True,
    )
    full = run_backtest(prices, strategy)
    result = {
        "parameter_selection": method["parameter_selection"],
        "rolling": run_window_validation(prices, strategy, rolling),
        "walk_forward_expanding": run_window_validation(prices, strategy, expanding),
        "market_regimes": regime_metrics(full["equity_curve"], benchmark, validation["market_regime"]),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"rolling_windows": len(rolling), "expanding_windows": len(expanding)}, indent=2))


if __name__ == "__main__":
    main()
