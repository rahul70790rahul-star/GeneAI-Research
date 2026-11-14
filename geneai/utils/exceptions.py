"""Shared exceptions for GeneAI Research API clients."""
from __future__ import annotations

from typing import Any


class GeneAIError(Exception):
    """Base exception for GeneAI Research."""
    
    def __init__(self, message: str, code: str | None = None, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__.upper()
        self.details = details or {}


class DataSourceError(GeneAIError):
    """An external scientific data source returned an unusable response."""
    
    def __init__(
        self,
        message: str,
        source: str | None = None,
        status_code: int | None = None,
        response_body: str | None = None,
    ):
        super().__init__(message, code="DATA_SOURCE_ERROR")
        self.source = source
        self.status_code = status_code
        self.response_body = response_body
        self.details.update({
            "source": source,
            "status_code": status_code,
            "response_body": response_body[:500] if response_body else None,
        })


class RateLimitError(GeneAIError):
    """Rate limit exceeded for an API."""
    
    def __init__(
        self,
        message: str,
        source: str | None = None,
        retry_after: float | None = None,
        limit: int | None = None,
        window: str | None = None,
    ):
        super().__init__(message, code="RATE_LIMIT_ERROR")
        self.source = source
        self.retry_after = retry_after
        self.limit = limit
        self.window = window
        self.details.update({
            "source": source,
            "retry_after": retry_after,
            "limit": limit,
            "window": window,
        })


class AuthenticationError(GeneAIError):
    """Authentication failed for an API."""
    
    def __init__(
        self,
        message: str,
        source: str | None = None,
        auth_type: str | None = None,
    ):
        super().__init__(message, code="AUTHENTICATION_ERROR")
        self.source = source
        self.auth_type = auth_type
        self.details.update({
            "source": source,
            "auth_type": auth_type,
        })


class ValidationError(GeneAIError):
    """Input validation failed."""
    
    def __init__(
        self,
        message: str,
        field: str | None = None,
        value: Any | None = None,
    ):
        super().__init__(message, code="VALIDATION_ERROR")
        self.field = field
        self.value = value
        self.details.update({
            "field": field,
            "value": str(value)[:200] if value is not None else None,
        })


class ConfigurationError(GeneAIError):
    """Configuration error."""
    
    def __init__(
        self,
        message: str,
        config_key: str | None = None,
    ):
        super().__init__(message, code="CONFIGURATION_ERROR")
        self.config_key = config_key
        self.details.update({
            "config_key": config_key,
        })


class CacheError(GeneAIError):
    """Cache operation failed."""
    
    def __init__(
        self,
        message: str,
        operation: str | None = None,
        key: str | None = None,
    ):
        super().__init__(message, code="CACHE_ERROR")
        self.operation = operation
        self.key = key
        self.details.update({
            "operation": operation,
            "key": key,
        })