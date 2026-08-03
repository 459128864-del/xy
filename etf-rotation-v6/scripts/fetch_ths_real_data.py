#!/usr/bin/env python3
"""Fetch configured ETF daily prices through the official iFinD HTTP API.

The command reads credentials only from environment variables.  It does not
print or persist access/refresh tokens.  The current command intentionally
supports the configured fixed research universe only; a historical all-ETF
catalogue requires a separately confirmed THS Universe protocol.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data_pipeline import validate_price_data, write_dataset  # noqa: E402
from src.data_provider import Adjustment, PriceProvider, create_price_provider  # noqa: E402


def build_ths_dataset(
    config: dict,
    provider: PriceProvider,
) -> tuple[pd.DataFrame, dict[str, object]]:
    if config.get("universe_scope") != "fixed_research_universe":
        raise ValueError(
            "THS price entry currently supports fixed_research_universe only; "
            "the all-ETF THS Universe protocol is not confirmed"
        )
    universe = config.get("universe")
    if not isinstance(universe, list) or not universe:
        raise ValueError("data-source config must contain a non-empty universe")
    symbols = [str(item["symbol"]) for item in universe]
    adjustment = Adjustment(str(config["adjust"]))
    daily = provider.get_daily_price(
        symbols,
        start_date=pd.Timestamp(str(config["start_date"])).date(),
        end_date=pd.Timestamp(str(config["end_date"])).date(),
        adjustment=adjustment,
    )
    prices = provider.as_backtest_prices(daily)
    metadata = pd.DataFrame(
        [
            {
                "symbol": str(item["symbol"]),
                "name": str(item["name"]),
                "category": str(item["category"]),
            }
            for item in universe
        ]
    )
    prices = prices.drop(columns=["name", "category"], errors="ignore").merge(
        metadata,
        on="symbol",
        how="left",
        validate="many_to_one",
    )
    prices = prices.loc[
        :, ["date", "symbol", "name", "category", "close", "adjustment", "source"]
    ].sort_values(["symbol", "date"]).reset_index(drop=True)
    summary = validate_price_data(prices)
    return prices, summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path, default=ROOT / "config/data_sources.yaml"
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    provider = create_price_provider("ths")
    prices, summary = build_ths_dataset(config, provider)

    manifest_config = dict(config)
    manifest_config["provider"] = "tonghuashun_ifind_http"
    manifest_config["interface"] = "cmd_history_quotation"
    output = args.output or ROOT / config["output"]
    manifest = args.manifest or ROOT / config["manifest"]
    write_dataset(
        prices,
        summary,
        output_path=output,
        manifest_path=manifest,
        config=manifest_config,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
