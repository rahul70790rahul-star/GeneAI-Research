"""Thread-safe rate limiter for API clients."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from geneai.utils.exceptions import RateLimitError


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    requests_per_second: float = 0.0  # 0 = no limit
    burst_allowance: int = 0  # Additional requests allowed in burst
    retry_status_codes: frozenset[int] = field(
        default_factory=lambda: frozenset({429, 500, 502, 503, 504})
    )


class RateLimiter:
    """Thread-safe rate limiter with per-host tracking.
    
    Usage:
        limiter = RateLimiter(default_config=RateLimitConfig(requests_per_second=5.0))
        limiter.configure_host("api.example.com", RateLimitConfig(requests_per_second=10.0))
        
        with limiter.acquire("api.example.com"):
            response = requests.get("https://api.example.com/data")
    """
    
    _default_config = RateLimitConfig(requests_per_second=0.0)  # No limit by default
    _host_configs: dict[str, RateLimitConfig] = {}
    _last_request: dict[str, float] = {}
    _burst_tokens: dict[str, int] = {}
    _lock = threading.RLock()
    
    @classmethod
    def configure_host(cls, host: str, config: RateLimitConfig) -> None:
        """Configure rate limit for a specific host."""
        with cls._lock:
            cls._host_configs[host] = config
            cls._burst_tokens[host] = config.burst_allowance
    
    @classmethod
    def configure_default(cls, config: RateLimitConfig) -> None:
        """Configure default rate limit for hosts without specific config."""
        with cls._lock:
            cls._default_config = config
    
    @classmethod
    def get_interval(cls, host: str) -> float:
        """Get the minimum interval between requests for a host (in seconds)."""
        config = cls._host_configs.get(host, cls._default_config)
        if config.requests_per_second <= 0:
            return 0.0
        return 1.0 / config.requests_per_second
    
    @classmethod
    def acquire(cls, host: str, timeout: float = 30.0) -> "RateLimitContext":
        """Acquire a rate limit slot for a host.
        
        Args:
            host: The hostname to acquire a slot for
            timeout: Maximum time to wait for a slot (seconds)
            
        Returns:
            RateLimitContext for use with 'with' statement
            
        Raises:
            RateLimitError: If timeout is exceeded
        """
        return RateLimitContext(host, timeout)
    
    @classmethod
    def wait_if_needed(cls, host: str) -> None:
        """Wait if necessary to respect rate limits (blocking call)."""
        interval = cls.get_interval(host)
        if interval <= 0:
            return
            
        with cls._lock:
            now = time.monotonic()
            last = cls._last_request.get(host, 0.0)
            wait = interval - (now - last)
            
            if wait > 0:
                time.sleep(wait)
                now = time.monotonic()
            
            cls._last_request[host] = now


class RateLimitContext:
    """Context manager for rate limiting."""
    
    def __init__(self, host: str, timeout: float):
        self.host = host
        self.timeout = timeout
        self._acquired = False
    
    def __enter__(self) -> None:
        interval = RateLimiter.get_interval(self.host)
        if interval <= 0:
            return
            
        start = time.monotonic()
        while True:
            with RateLimiter._lock:
                now = time.monotonic()
                last = RateLimiter._last_request.get(self.host, 0.0)
                wait = interval - (now - last)
                
                if wait <= 0:
                    RateLimiter._last_request[self.host] = now
                    self._acquired = True
                    return
            
            if time.monotonic() - start >= self.timeout:
                raise RateLimitError(
                    f"Rate limit timeout for {self.host}",
                    source=self.host,
                    retry_after=wait,
                )
            
            # Sleep a bit before retrying
            time.sleep(min(0.01, wait))
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    return RateLimiter


# Pre-configured rate limits for common scientific APIs
DEFAULT_RATE_LIMITS = {
    "api.platform.opentargets.org": RateLimitConfig(requests_per_second=5.0, burst_allowance=10),
    "eutils.ncbi.nlm.nih.gov": RateLimitConfig(requests_per_second=3.0, burst_allowance=5),
    "rest.ensembl.org": RateLimitConfig(requests_per_second=4.0, burst_allowance=8),
    "rest.uniprot.org": RateLimitConfig(requests_per_second=7.0, burst_allowance=10),
    "www.ebi.ac.uk": RateLimitConfig(requests_per_second=7.0, burst_allowance=10),
    "alphafold.ebi.ac.uk": RateLimitConfig(requests_per_second=5.0, burst_allowance=5),
    "data.rcsb.org": RateLimitConfig(requests_per_second=5.0, burst_allowance=5),
    "files.rcsb.org": RateLimitConfig(requests_per_second=5.0, burst_allowance=5),
    "reactome.org": RateLimitConfig(requests_per_second=4.0, burst_allowance=5),
    "search.rcsb.org": RateLimitConfig(requests_per_second=4.0, burst_allowance=5),
    "version-12-5.string-db.org": RateLimitConfig(requests_per_second=1.0, burst_allowance=2),
    "pubchem.ncbi.nlm.nih.gov": RateLimitConfig(requests_per_second=5.0, burst_allowance=10),
    "www.ebi.ac.uk": RateLimitConfig(requests_per_second=7.0, burst_allowance=10),
    "admetmesh.scbdd.com": RateLimitConfig(requests_per_second=1.0, burst_allowance=2),
    "tripod.nih.gov": RateLimitConfig(requests_per_second=2.0, burst_allowance=3),
    "go.drugbank.com": RateLimitConfig(requests_per_second=1.0, burst_allowance=1),
}

def apply_default_rate_limits() -> None:
    """Apply default rate limits for known scientific APIs."""
    for host, config in DEFAULT_RATE_LIMITS.items():
        RateLimiter.configure_host(host, config)


# Apply default rate limits on module import
apply_default_rate_limits()