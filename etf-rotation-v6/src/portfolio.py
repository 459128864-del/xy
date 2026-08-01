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
    if top_n < 1:
        raise ValueError("top_n must be positive")
    if not 0.0 < max_position <= 1.0:
        raise ValueError("max_position must be in (0, 1]")
    if any(not 0.0 <= float(value) <= 1.0 for value in exposure_by_regime.values()):
        raise ValueError("regime exposures must be between zero and one")
    merged = scored.merge(regimes[["date", "regime"]], on="date", how="left")
    rows: list[dict[str, object]] = []
    for date, group in merged.groupby("date", sort=True):
        regime = group["regime"].iloc[0]
        exposure = float(exposure_by_regime.get(regime, 0.0))
        selected = group[group["score"].ge(min_score)].nsmallest(top_n, "rank")
        if selected.empty:
            continue
        # Position limits take precedence over filling the regime exposure.
        # Any capped residual remains explicit cash; it is never redistributed.
        weight = min(exposure / len(selected), max_position)
        rows.extend(
            {"date": date, "symbol": symbol, "weight": weight, "regime": regime}
            for symbol in selected["symbol"]
        )
    return pd.DataFrame(rows, columns=["date", "symbol", "weight", "regime"])
