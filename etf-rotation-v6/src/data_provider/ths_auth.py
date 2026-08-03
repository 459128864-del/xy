"""Shared THS credential container with secret-safe representation."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from .exceptions import ProviderAuthenticationError


THS_ENVIRONMENT_VARIABLES = (
    "THS_APP_KEY",
    "THS_APP_SECRET",
    "THS_ACCESS_TOKEN",
)


@dataclass(frozen=True, repr=False)
class THSCredentials:
    """Credentials loaded only from process environment; repr is disabled."""

    app_key: str
    app_secret: str
    access_token: str

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> "THSCredentials":
        values = os.environ if environment is None else environment
        missing = [name for name in THS_ENVIRONMENT_VARIABLES if not values.get(name)]
        if missing:
            raise ProviderAuthenticationError(
                f"missing THS credential environment variables: {missing}"
            )
        return cls(
            app_key=values["THS_APP_KEY"],
            app_secret=values["THS_APP_SECRET"],
            access_token=values["THS_ACCESS_TOKEN"],
        )
