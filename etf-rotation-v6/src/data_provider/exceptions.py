"""Errors raised by market-data providers without exposing credentials."""


class DataProviderError(RuntimeError):
    """Base error for provider configuration, transport, and data failures."""


class ProviderAuthenticationError(DataProviderError):
    """Required credential environment variables are missing or invalid."""


class ProviderNotConnectedError(DataProviderError):
    """The provider has no real API transport attached yet."""


class ProviderRequestError(DataProviderError):
    """A provider request failed before a usable response was received."""


class ProviderDataError(DataProviderError):
    """A provider response cannot satisfy the canonical V6 data contract."""


class UnsupportedDataProviderError(DataProviderError):
    """The requested provider adapter has not been registered."""
