"""Provider registry used by data-entry scripts, never by the backtest engine."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .base import PriceProvider
from .exceptions import UnsupportedDataProviderError
from .ths_price_provider import THSPriceProvider, THSPriceTransport


ProviderBuilder = Callable[..., PriceProvider]
_PROVIDER_BUILDERS: dict[str, ProviderBuilder] = {}


def register_price_provider(name: str, builder: ProviderBuilder) -> None:
    """Register a price-only adapter; Universe providers use another boundary."""
    key = name.strip().lower()
    if not key:
        raise ValueError("provider name cannot be blank")
    _PROVIDER_BUILDERS[key] = builder


def _build_ths(
    *,
    environment: Mapping[str, str] | None = None,
    transport: THSPriceTransport | None = None,
    **_: Any,
) -> PriceProvider:
    return THSPriceProvider.from_environment(
        environment=environment,
        transport=transport,
    )


register_price_provider("ths", _build_ths)
register_price_provider("tonghuashun", _build_ths)


def create_price_provider(name: str, **kwargs: Any) -> PriceProvider:
    """Create a selected price adapter without any Universe responsibility."""
    key = name.strip().lower()
    builder = _PROVIDER_BUILDERS.get(key)
    if builder is None:
        available = ", ".join(sorted(_PROVIDER_BUILDERS))
        raise UnsupportedDataProviderError(
            f"data provider {name!r} is not registered; available: {available}"
        )
    return builder(**kwargs)


# Compatibility names remain price-only.
register_data_provider = register_price_provider
create_data_provider = create_price_provider
