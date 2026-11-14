"""Small bounded in-process TTL cache for public API response objects."""
from __future__ import annotations

import json
import threading
import time
from collections import OrderedDict
from copy import deepcopy
from functools import wraps
from typing import Any, Callable, TypeVar, cast

F = TypeVar("F", bound=Callable[..., Any])


def ttl_cache(*, ttl_seconds: int = 21_600, max_entries: int = 128) -> Callable[[F], F]:
    """Cache successful JSON-like results; callers receive independent copies."""
    if ttl_seconds < 1 or max_entries < 1:
        raise ValueError("Cache TTL and entry limit must be positive.")

    def decorate(function: F) -> F:
        entries: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        lock = threading.RLock()

        @wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            key = json.dumps([args, kwargs], sort_keys=True, default=str, separators=(",", ":"))
            now = time.monotonic()
            with lock:
                cached = entries.get(key)
                if cached and cached[0] > now:
                    entries.move_to_end(key)
                    return deepcopy(cached[1])
                if cached:
                    entries.pop(key, None)
            value = function(*args, **kwargs)
            stored = deepcopy(value)
            with lock:
                entries[key] = (time.monotonic() + ttl_seconds, stored)
                entries.move_to_end(key)
                while len(entries) > max_entries:
                    entries.popitem(last=False)
            return deepcopy(value)

        def clear() -> None:
            with lock:
                entries.clear()

        setattr(wrapped, "cache_clear", clear)
        return cast(F, wrapped)

    return decorate
