"""Cross-sectional factor scoring."""

from __future__ import annotations

import pandas as pd


def score_factors(
    factors: pd.DataFrame,
    weights: dict[str, float],
    *,
    minimum_history: int = 1,
) -> pd.DataFrame:
    if minimum_history < 1:
        raise ValueError("minimum_history must be at least 1")

    frame = factors.copy()
    directions = {
        "momentum": (True, "momentum"),
        "efficiency": (True, "efficiency"),
        "volatility": (False, "low_volatility"),
        "drawdown": (True, "low_drawdown"),
    }
    required_factors = list(directions)
    frame["history_count"] = frame.groupby("symbol").cumcount().add(1)
    frame["eligible"] = (
        frame["history_count"].ge(minimum_history)
        & frame[required_factors].notna().all(axis=1)
    )
    frame = frame.loc[frame["eligible"]].copy()
    scores = []
    for name, (higher_is_better, weight_name) in directions.items():
        column = f"{name}_score"
        frame[column] = frame.groupby("date")[name].rank(
            pct=True, ascending=higher_is_better, na_option="bottom"
        )
        scores.append(frame[column] * float(weights[weight_name]))
    frame["score"] = sum(scores)
    frame["rank"] = frame.groupby("date")["score"].rank(
        method="first", ascending=False
    )
    return frame
