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
    "THS_REFRESH_TOKEN",
)


@dataclass(frozen=True, repr=False)
class THSCredentials:
    """Secret-safe credentials loaded only from process environment.

    The iFinD HTTP API authenticates data requests with ``access_token`` and
    obtains the current valid token with ``refresh_token``.  ``app_key`` and
    ``app_secret`` remain optional compatibility fields for deployments that
    already expose them; the HTTP transport never sends them.
    """

    app_key: str | None = None
    app_secret: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> "THSCredentials":
        values = os.environ if environment is None else environment
        access_token = _optional_env_value(values, "THS_ACCESS_TOKEN")
        refresh_token = _optional_env_value(values, "THS_REFRESH_TOKEN")
        if access_token is None and refresh_token is None:
            raise ProviderAuthenticationError(
                "THS_ACCESS_TOKEN or THS_REFRESH_TOKEN must be set"
            )
        return cls(
            app_key=_optional_env_value(values, "THS_APP_KEY"),
            app_secret=_optional_env_value(values, "THS_APP_SECRET"),
            access_token=access_token,
            refresh_token=refresh_token,
        )


def _optional_env_value(values: Mapping[str, str], name: str) -> str | None:
    value = values.get(name)
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
