"""Error recovery module for Autonomous Bioinformatics Agent."""
from __future__ import annotations

import logging
import random
import time
from typing import Any

logger = logging.getLogger(__name__)


class ErrorRecovery:
    """
    Handle error recovery with exponential backoff and parameter adjustment.
    """

    def __init__(
        self,
        max_retries: int = 3,
        backoff_base: float = 2.0,
        backoff_max: float = 60.0,
        jitter: bool = True,
    ):
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self.jitter = jitter
        self.logger = logging.getLogger(__name__)

    def get_backoff(self, attempt: int) -> float:
        """
        Calculate backoff delay for a retry attempt.

        Args:
            attempt: Retry attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        delay = min(self.backoff_base ** attempt, self.backoff_max)
        if self.jitter:
            delay *= (0.5 + random.random())  # 0.5x to 1.5x
        return delay

    def should_retry(self, error: Exception, attempt: int) -> bool:
        """
        Determine if an error should trigger a retry.

        Args:
            error: The exception that occurred
            attempt: Current attempt number

        Returns:
            True if should retry
        """
        if attempt >= self.max_retries:
            return False

        # Retry on transient errors
        transient_errors = (
            ConnectionError,
            TimeoutError,
            IOError,
        )

        # Check error message for transient patterns
        error_str = str(error).lower()
        transient_patterns = [
            "timeout",
            "connection",
            "network",
            "temporary",
            "rate limit",
            "too many requests",
            "service unavailable",
            "503",
            "504",
        ]

        if isinstance(error, transient_errors):
            return True

        if any(pattern in error_str for pattern in transient_patterns):
            return True

        return False

    def adjust_parameters(
        self,
        params: dict[str, Any],
        error: Exception,
        attempt: int,
    ) -> dict[str, Any]:
        """
        Adjust parameters based on error and attempt.

        Args:
            params: Original parameters
            error: The exception that occurred
            attempt: Current attempt number

        Returns:
            Adjusted parameters
        """
        adjusted = params.copy()
        error_str = str(error).lower()

        # Adjust for rate limiting
        if "rate limit" in error_str or "too many requests" in error_str:
            adjusted.setdefault("rate_limit_delay", 1.0)
            adjusted["rate_limit_delay"] *= 2

        # Adjust for timeout
        if "timeout" in error_str:
            adjusted.setdefault("timeout", 30)
            adjusted["timeout"] = min(adjusted["timeout"] * 1.5, 300)

        # Adjust for memory issues
        if "memory" in error_str or "oom" in error_str:
            if "batch_size" in adjusted:
                adjusted["batch_size"] = max(adjusted["batch_size"] // 2, 1)

        # Add attempt number for tool awareness
        adjusted["_retry_attempt"] = attempt

        logger.info("Adjusted parameters for attempt %d: %s", attempt, adjusted)
        return adjusted

    def classify_error(self, error: Exception) -> str:
        """
        Classify error type for reporting.

        Returns:
            Error category string
        """
        error_str = str(error).lower()

        if "timeout" in error_str:
            return "timeout"
        elif "connection" in error_str or "network" in error_str:
            return "network"
        elif "rate limit" in error_str or "too many requests" in error_str:
            return "rate_limit"
        elif "memory" in error_str or "oom" in error_str:
            return "memory"
        elif "permission" in error_str or "unauthorized" in error_str or "403" in error_str:
            return "permission"
        elif "not found" in error_str or "404" in error_str:
            return "not_found"
        elif "validation" in error_str or "invalid" in error_str:
            return "validation"
        else:
            return "unknown"


class RecoveryStrategy:
    """Predefined recovery strategies for common tool errors."""

    STRATEGIES = {
        "ncbi_api": {
            "timeout": {"action": "increase_timeout", "factor": 2},
            "rate_limit": {"action": "exponential_backoff", "base_delay": 5},
            "network": {"action": "retry_with_backoff"},
        },
        "pubchem_api": {
            "timeout": {"action": "increase_timeout", "factor": 1.5},
            "rate_limit": {"action": "exponential_backoff", "base_delay": 2},
        },
        "chembl_api": {
            "timeout": {"action": "increase_timeout", "factor": 2},
            "rate_limit": {"action": "exponential_backoff", "base_delay": 3},
        },
        "docking": {
            "memory": {"action": "reduce_batch_size", "factor": 0.5},
            "timeout": {"action": "increase_timeout", "factor": 2},
        },
        "ml_training": {
            "memory": {"action": "reduce_batch_size", "factor": 0.5},
            "timeout": {"action": "reduce_epochs", "factor": 0.5},
        },
    }

    @classmethod
    def get_strategy(cls, tool_category: str, error_type: str) -> dict[str, Any] | None:
        """Get recovery strategy for tool category and error type."""
        return cls.STRATEGIES.get(tool_category, {}).get(error_type)

    @classmethod
    def apply_strategy(cls, params: dict[str, Any], strategy: dict[str, Any]) -> dict[str, Any]:
        """Apply a recovery strategy to parameters."""
        adjusted = params.copy()
        action = strategy.get("action")

        if action == "increase_timeout":
            factor = strategy.get("factor", 2)
            adjusted.setdefault("timeout", 30)
            adjusted["timeout"] = min(adjusted["timeout"] * factor, 300)

        elif action == "exponential_backoff":
            base_delay = strategy.get("base_delay", 1)
            adjusted.setdefault("retry_delay", base_delay)

        elif action == "reduce_batch_size":
            factor = strategy.get("factor", 0.5)
            if "batch_size" in adjusted:
                adjusted["batch_size"] = max(int(adjusted["batch_size"] * factor), 1)

        elif action == "reduce_epochs":
            factor = strategy.get("factor", 0.5)
            if "epochs" in adjusted:
                adjusted["epochs"] = max(int(adjusted["epochs"] * factor), 1)

        return adjusted