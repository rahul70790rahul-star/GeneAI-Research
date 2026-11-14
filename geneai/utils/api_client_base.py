"""Base API client with retry, rate limiting, and error handling."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import requests

from geneai.utils.exceptions import (
    DataSourceError,
    RateLimitError,
    AuthenticationError,
    ValidationError,
)
from geneai.utils.rate_limiter import RateLimiter, RateLimitConfig


logger = logging.getLogger(__name__)


@dataclass
class APIClientConfig:
    """Configuration for API client."""
    base_url: str
    timeout: int = 30
    max_retries: int = 3
    retry_backoff: float = 0.5
    default_headers: dict[str, str] = field(default_factory=dict)
    rate_limit_config: RateLimitConfig | None = None
    user_agent: str = "GeneAIResearch/1.0 (scientific research client)"
    verify_ssl: bool = True


class BaseAPIClient:
    """Base class for API clients with shared functionality.
    
    Features:
    - Automatic rate limiting per host
    - Exponential backoff retry logic
    - Standardized error handling
    - Request/response logging
    - JSON/XML response parsing
    
    Example:
        class MyClient(BaseAPIClient):
            def get_data(self, id: str):
                return self.get(f"/data/{id}")
    """
    
    def __init__(self, config: APIClientConfig):
        self.config = config
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": config.user_agent,
            **config.default_headers,
        })
        
        # Configure rate limiter for this client's host
        host = urlparse(config.base_url).hostname or ""
        if config.rate_limit_config:
            RateLimiter.configure_host(host, config.rate_limit_config)
        elif not RateLimiter._host_configs.get(host):
            # Use a reasonable default if not configured
            RateLimiter.configure_host(host, RateLimitConfig(requests_per_second=5.0))
    
    @property
    def host(self) -> str:
        return urlparse(self.config.base_url).hostname or ""
    
    def _get_headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        """Get headers for request, merging defaults with extras."""
        headers = dict(self._session.headers)
        if extra:
            headers.update(extra)
        return headers
    
    def _apply_rate_limit(self) -> None:
        """Apply rate limiting for this client's host."""
        RateLimiter.wait_if_needed(self.host)
    
    def _handle_response(
        self,
        response: requests.Response,
        expect_json: bool = True,
        expect_xml: bool = False,
    ) -> Any:
        """Handle response with error checking and parsing."""
        # Check for rate limiting
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            try:
                delay = float(retry_after) if retry_after else None
            except (ValueError, TypeError):
                delay = None
            raise RateLimitError(
                f"Rate limited by {self.host}",
                source=self.host,
                retry_after=delay,
            )
        
        # Check for authentication errors
        if response.status_code in (401, 403):
            raise AuthenticationError(
                f"Authentication failed for {self.host}",
                source=self.host,
            )
        
        # Check for client errors
        if 400 <= response.status_code < 500:
            body = response.text[:500] if response.text else ""
            raise DataSourceError(
                f"{self.host} returned HTTP {response.status_code}: {body}",
                source=self.host,
                status_code=response.status_code,
                response_body=response.text,
            )
        
        # Check for server errors
        if response.status_code >= 500:
            body = response.text[:500] if response.text else ""
            raise DataSourceError(
                f"{self.host} server error {response.status_code}: {body}",
                source=self.host,
                status_code=response.status_code,
                response_body=response.text,
            )
        
        # Parse response
        if expect_xml:
            return response.text
        
        if expect_json:
            try:
                return response.json()
            except (ValueError, requests.JSONDecodeError) as exc:
                raise DataSourceError(
                    f"{self.host} returned invalid JSON: {exc}",
                    source=self.host,
                    status_code=response.status_code,
                    response_body=response.text[:500],
                ) from exc
        
        return response.text
    
    def _request_with_retry(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        data: Any | None = None,
        headers: dict[str, str] | None = None,
        expect_json: bool = True,
        expect_xml: bool = False,
        timeout: int | None = None,
        **kwargs: Any,
    ) -> Any:
        """Execute request with retry logic and rate limiting."""
        url = f"{self.config.base_url.rstrip('/')}/{path.lstrip('/')}"
        timeout = timeout or self.config.timeout
        request_headers = self._get_headers(headers)
        
        last_error: Exception | None = None
        
        for attempt in range(self.config.max_retries + 1):
            self._apply_rate_limit()
            
            try:
                response = self._session.request(
                    method,
                    url,
                    params=params,
                    json=json,
                    data=data,
                    headers=request_headers,
                    timeout=timeout,
                    verify=self.config.verify_ssl,
                    **kwargs,
                )
            except requests.Timeout as exc:
                last_error = exc
                if attempt < self.config.max_retries:
                    time.sleep(self.config.retry_backoff * (2 ** attempt))
                    continue
                raise DataSourceError(
                    f"Request to {self.host} timed out after {self.config.max_retries + 1} attempts",
                    source=self.host,
                ) from exc
            except requests.RequestException as exc:
                last_error = exc
                if attempt < self.config.max_retries:
                    time.sleep(self.config.retry_backoff * (2 ** attempt))
                    continue
                raise DataSourceError(
                    f"Request to {self.host} failed: {exc}",
                    source=self.host,
                ) from exc
            
            # Check if we should retry based on status code
            if response.status_code in RateLimiter._default_config.retry_status_codes:
                if attempt < self.config.max_retries:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        delay = float(retry_after) if retry_after else self.config.retry_backoff * (2 ** attempt)
                    except (ValueError, TypeError):
                        delay = self.config.retry_backoff * (2 ** attempt)
                    time.sleep(min(delay, 30.0))  # Cap at 30 seconds
                    continue
            
            # Handle response (will raise on error status codes)
            return self._handle_response(response, expect_json, expect_xml)
        
        # If we got here, all retries failed
        raise DataSourceError(
            f"Request to {self.host} failed after {self.config.max_retries + 1} attempts: {last_error}",
            source=self.host,
        ) from last_error
    
    # Convenience methods
    def get(self, path: str, **kwargs: Any) -> Any:
        """GET request."""
        return self._request_with_retry("GET", path, **kwargs)
    
    def post(self, path: str, **kwargs: Any) -> Any:
        """POST request."""
        return self._request_with_retry("POST", path, **kwargs)
    
    def put(self, path: str, **kwargs: Any) -> Any:
        """PUT request."""
        return self._request_with_retry("PUT", path, **kwargs)
    
    def delete(self, path: str, **kwargs: Any) -> Any:
        """DELETE request."""
        return self._request_with_retry("DELETE", path, **kwargs)
    
    def patch(self, path: str, **kwargs: Any) -> Any:
        """PATCH request."""
        return self._request_with_retry("PATCH", path, **kwargs)
    
    def close(self) -> None:
        """Close the underlying session."""
        self._session.close()
    
    def __enter__(self) -> "BaseAPIClient":
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()