"""Translate scores and regimes into constrained target weights."""

from __future__ import annotations

import pandas as pd


def construct_weights(
    scored: pd.DataFrame,
    regimes: pd.DataFrame,
    *,
    top_n: int,
    min_score: float,
    max_position: float,
    exposure_by_regime: dict[str, float],
) -> pd.DataFrame:
    merged = scored.merge(regimes[["date", "regime"]], on="date", how="left")
    rows: list[dict[str, object]] = []
    for date, group in merged.groupby("date", sort=True):
        regime = group["regime"].iloc[0]
        exposure = float(exposure_by_regime.get(regime, 0.0))
        selected = group[group["score"].ge(min_score)].nsmallest(top_n, "rank")
        if selected.empty:
            continue
        weight = min(exposure / len(selected), max_position)
        rows.extend(
            {"date": date, "symbol": symbol, "weight": weight, "regime": regime}
            for symbol in selected["symbol"]
        )
    return pd.DataFrame(rows, columns=["date", "symbol", "weight", "regime"])
