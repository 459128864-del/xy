"""Cross-sectional factor scoring."""

from __future__ import annotations

import pandas as pd


def score_factors(factors: pd.DataFrame, weights: dict[str, float]) -> pd.DataFrame:
    frame = factors.copy()
    directions = {
        "momentum": (True, "momentum"),
        "efficiency": (True, "efficiency"),
        "volatility": (False, "low_volatility"),
        "drawdown": (True, "low_drawdown"),
    }
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
