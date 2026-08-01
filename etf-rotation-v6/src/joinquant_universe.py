"""JoinQuant adapter for an all-history Shanghai/Shenzhen ETF catalogue."""

from __future__ import annotations

from datetime import date
from typing import Callable

import pandas as pd


KNOWN_DELISTED_ETFS = {"510220"}


def normalize_joinquant_etf_catalog(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize ``get_all_securities(['fund'], date=None)`` output.

    Passing ``date=None`` is essential: a dated query only returns securities
    listed on that date and would recreate survivorship bias.
    """
    required = {"display_name", "start_date", "end_date", "type"}
    missing = required.difference(raw.columns)
    if missing:
        raise ValueError(f"JoinQuant catalogue missing columns: {sorted(missing)}")
    if raw.index.has_duplicates:
        raise ValueError("JoinQuant catalogue contains duplicate security codes")

    etfs = raw.loc[raw["type"].eq("etf"), [
        "display_name", "start_date", "end_date"
    ]].copy()
    if etfs.empty:
        raise ValueError("JoinQuant catalogue contains no ETFs")
    codes = etfs.index.to_series().astype(str)
    valid_exchange = codes.str.endswith((".XSHG", ".XSHE"))
    if not valid_exchange.all():
        invalid = sorted(codes.loc[~valid_exchange].tolist())
        raise ValueError(f"unsupported JoinQuant ETF exchange codes: {invalid}")

    catalog = pd.DataFrame({
        "symbol": codes.str.split(".").str[0].values,
        "name": etfs["display_name"].astype(str).str.strip().values,
        "listing_date": pd.to_datetime(etfs["start_date"], errors="raise").values,
        "delisting_date": pd.to_datetime(etfs["end_date"], errors="raise").values,
        "source": "joinquant:get_all_securities(fund,date=None)",
    })
    # JoinQuant uses a far-future sentinel for active securities.
    catalog.loc[catalog["delisting_date"].dt.year >= 2100, "delisting_date"] = pd.NaT
    catalog = catalog.sort_values("symbol").reset_index(drop=True)
    if catalog["symbol"].duplicated().any():
        raise ValueError("normalized ETF catalogue contains duplicate symbols")
    return catalog


def fetch_joinquant_etf_catalog(
    get_all_securities: Callable[..., pd.DataFrame],
    *,
    required_delisted: set[str] | None = None,
) -> pd.DataFrame:
    """Fetch all historical funds and reject a current-only response."""
    raw = get_all_securities(types=["fund"], date=None)
    catalog = normalize_joinquant_etf_catalog(raw)
    required = required_delisted or KNOWN_DELISTED_ETFS
    actual_delisted = set(
        catalog.loc[catalog["delisting_date"].notna(), "symbol"]
    )
    missing = sorted(required - actual_delisted)
    if missing:
        raise ValueError(
            f"JoinQuant response is not all-history; missing known delisted ETFs: {missing}"
        )
    return catalog


def build_joinquant_metadata(catalog: pd.DataFrame, *, as_of: date) -> dict[str, object]:
    return {
        "provider_id": "joinquant_jqdata",
        "source_name": "JoinQuant JQData get_all_securities",
        "source_url": "https://www.joinquant.com/help/api/doc?id=10029&name=JQDatadoc",
        "authoritative": True,
        "scope": "all_sh_sz_etfs",
        "complete_through": as_of.isoformat(),
        "expected_symbol_count": int(len(catalog)),
    }
