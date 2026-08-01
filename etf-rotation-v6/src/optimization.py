"""Single-parameter V6.1 research with a locked final holdout."""

from __future__ import annotations

import copy

import pandas as pd

from .backtest import run_backtest
from .validation import return_metrics


def evaluate_period(curve: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> dict[str, float | int]:
    period = curve.loc[curve["date"].between(start, end)]
    metrics = return_metrics(period["return"])
    metrics["average_turnover"] = float(period["turnover"].mean())
    metrics["cumulative_cost"] = float(period["total_cost"].sum())
    annualized = float(metrics["annualized_return"])
    max_drawdown = float(metrics["max_drawdown"])
    metrics["calmar"] = annualized / abs(max_drawdown) if max_drawdown < 0 else 0.0
    return metrics


def config_with_defense_exposure(base_config: dict, exposure: float) -> dict:
    if not 0.0 <= exposure <= 1.0:
        raise ValueError("defense exposure must be between zero and one")
    candidate = copy.deepcopy(base_config)
    candidate["regime"]["exposure"]["defense"] = float(exposure)
    return candidate


def select_development_candidate(
    development_results: list[dict[str, object]],
    *,
    baseline_exposure: float,
    minimum_annualized_return: float,
    maximum_sharpe_degradation_from_baseline: float,
) -> dict[str, object]:
    """Select by development risk only; holdout results are not accepted here."""
    baseline = next(row for row in development_results if row["exposure"] == baseline_exposure)
    baseline_sharpe = float(baseline["metrics"]["sharpe"])
    eligible = [
        row for row in development_results
        if float(row["metrics"]["annualized_return"]) >= minimum_annualized_return
        and float(row["metrics"]["sharpe"]) >= baseline_sharpe - maximum_sharpe_degradation_from_baseline
    ]
    if not eligible:
        return baseline
    return max(
        eligible,
        key=lambda row: (float(row["metrics"]["max_drawdown"]), float(row["metrics"]["sharpe"])),
    )


def run_single_factor_research(prices: pd.DataFrame, base_config: dict, research: dict) -> dict[str, object]:
    dates = pd.DatetimeIndex(prices["date"].drop_duplicates()).sort_values()
    development_start = dates.min()
    development_end = pd.Timestamp(research["development_end"])
    holdout_start = pd.Timestamp(research["holdout_start"])
    holdout_end = dates.max()
    if development_end >= holdout_start:
        raise ValueError("development must end before holdout starts")
    development_results = []
    development_prices = prices.loc[prices["date"].le(development_end)]
    for raw_exposure in research["candidates"]:
        exposure = float(raw_exposure)
        result = run_backtest(
            development_prices, config_with_defense_exposure(base_config, exposure)
        )
        development_results.append({
            "exposure": exposure,
            "metrics": evaluate_period(result["equity_curve"], development_start, development_end),
        })
    baseline_exposure = float(base_config["regime"]["exposure"]["defense"])
    selection = research["selection"]
    selected = select_development_candidate(
        development_results,
        baseline_exposure=baseline_exposure,
        minimum_annualized_return=float(selection["minimum_annualized_return"]),
        maximum_sharpe_degradation_from_baseline=float(selection["maximum_sharpe_degradation_from_baseline"]),
    )
    selected_exposure = float(selected["exposure"])
    baseline_curve = run_backtest(prices, base_config)["equity_curve"]
    selected_curve = run_backtest(
        prices, config_with_defense_exposure(base_config, selected_exposure)
    )["equity_curve"]
    return {
        "single_parameter": "regime.exposure.defense",
        "development_start": development_start.date().isoformat(),
        "development_end": development_end.date().isoformat(),
        "holdout_start": holdout_start.date().isoformat(),
        "holdout_end": holdout_end.date().isoformat(),
        "baseline_exposure": baseline_exposure,
        "selected_exposure": selected_exposure,
        "development_results": development_results,
        "holdout_baseline": evaluate_period(baseline_curve, holdout_start, holdout_end),
        "holdout_selected": evaluate_period(selected_curve, holdout_start, holdout_end),
    }
