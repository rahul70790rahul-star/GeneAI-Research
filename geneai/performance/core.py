"""Performance Optimization - Phase 5.10 Core."""
from __future__ import annotations

import asyncio
import functools
import logging
import os
import sys
import tempfile
import threading
import time
import weakref
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Optional, TypeVar
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import psutil

logger = logging.getLogger(__name__)

T = TypeVar('T')


class CacheStrategy(Enum):
    """Cache eviction strategies."""
    LRU = "lru"
    LFU = "lfu"
    TTL = "ttl"
    FIFO = "fifo"


@dataclass
class CacheEntry:
    """Cache entry with metadata."""
    key: str
    value: Any
    created_at: float = field(default_factory=time.time)
    accessed_at: float = field(default_factory=time.time)
    access_count: int = 0
    ttl: float | None = None
    size: int = 0
    
    def is_expired(self) -> bool:
        if self.ttl is None:
            return False
        return time.time() - self.created_at > self.ttl
    
    def touch(self) -> None:
        self.accessed_at = time.time()
        self.access_count += 1


class LRUCache:
    """Thread-safe LRU cache with TTL support."""
    
    def __init__(self, max_size: int = 1000, default_ttl: float | None = None):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return default
            
            if entry.is_expired():
                del self._cache[key]
                self._misses += 1
                return default
            
            entry.touch()
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            return entry.value
    
    def set(self, key: str, value: Any, ttl: float | None = None, size: int = 0) -> None:
        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                entry.value = value
                entry.ttl = ttl if ttl is not None else self.default_ttl
                entry.size = size
                entry.touch()
                self._cache.move_to_end(key)
            else:
                # Evict if at capacity
                while len(self._cache) >= self.max_size:
                    self._cache.popitem(last=False)
                
                entry = CacheEntry(
                    key=key,
                    value=value,
                    ttl=ttl if ttl is not None else self.default_ttl,
                    size=size,
                )
                self._cache[key] = entry
    
    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
    
    def cleanup_expired(self) -> int:
        with self._lock:
            expired_keys = [
                k for k, v in self._cache.items() if v.is_expired()
            ]
            for k in expired_keys:
                del self._cache[k]
            return len(expired_keys)
    
    def stats(self) -> dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
                "memory_estimate": sum(e.size for e in self._cache.values()),
            }
    
    def __contains__(self, key: str) -> bool:
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return False
            if entry.is_expired():
                del self._cache[key]
                return False
            return True


class MultiLevelCache:
    """Multi-level cache (L1 memory, L2 disk/Redis)."""
    
    def __init__(self, l1_size: int = 100, l2_path: str | None = None):
        self.l1 = LRUCache(max_size=l1_size)
        self.l2_path = l2_path or os.path.join(tempfile.gettempdir(), "geneai_cache_l2")
        os.makedirs(self.l2_path, exist_ok=True)
    
    def get(self, key: str, default: Any = None) -> Any:
        # Try L1
        value = self.l1.get(key)
        if value is not None:
            return value
        
        # Try L2 (disk)
        value = self._get_from_l2(key)
        if value is not None:
            # Promote to L1
            self.l1.set(key, value)
            return value
        
        return default
    
    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        self.l1.set(key, value, ttl)
        self._set_in_l2(key, value, ttl)
    
    def stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        l1_stats = self.l1.stats()
        return {
            "l1": l1_stats,
            "l2": {
                "path": self.l2_path,
                "enabled": True,
            },
        }
    
    def _get_from_l2(self, key: str) -> Any | None:
        try:
            import pickle
            filepath = os.path.join(self.l2_path, f"{key}.cache")
            if os.path.exists(filepath):
                with open(filepath, 'rb') as f:
                    data = pickle.load(f)
                if data.get('ttl') and time.time() - data['created'] > data['ttl']:
                    os.remove(filepath)
                    return None
                return data['value']
        except Exception:
            pass
        return None
    
    def _set_in_l2(self, key: str, value: Any, ttl: float | None = None) -> None:
        try:
            import pickle
            filepath = os.path.join(self.l2_path, f"{key}.cache")
            data = {
                'value': value,
                'created': time.time(),
                'ttl': ttl,
            }
            with open(filepath, 'wb') as f:
                pickle.dump(data, f)
        except Exception as e:
            logger.error(f"L2 cache write failed: {e}")


class AsyncCache:
    """Async-compatible cache with background operations."""
    
    def __init__(self, max_size: int = 1000):
        self._cache = LRUCache(max_size)
        self._executor = ThreadPoolExecutor(max_workers=2)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Synchronous get for compatibility."""
        return self._cache.get(key, default)
    
    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        """Synchronous set for compatibility."""
        self._cache.set(key, value, ttl)
    
    async def get_async(self, key: str, default: Any = None) -> Any:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._cache.get, key, default)
    
    async def set_async(self, key: str, value: Any, ttl: float | None = None) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self._executor, self._cache.set, key, value, ttl)
    
    async def delete(self, key: str) -> bool:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._cache.delete, key)
    
    async def stats(self) -> dict[str, Any]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._cache.stats)


def cached(ttl: float = 300, max_size: int = 128, key_func: Callable | None = None):
    """Decorator for caching function results."""
    cache = LRUCache(max_size=max_size, default_ttl=ttl)
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = f"{func.__module__}.{func.__name__}:{args}:{frozenset(kwargs.items())}"
            
            # Try cache
            result = cache.get(cache_key)
            if result is not None:
                return result
            
            # Compute and cache
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            return result
        
        # Add cache management methods
        wrapper.cache = cache
        wrapper.clear_cache = cache.clear
        wrapper.cache_stats = cache.stats
        
        return wrapper
    return decorator


def async_cached(ttl: float = 300, max_size: int = 128):
    """Decorator for caching async function results."""
    cache = AsyncCache(max_size=max_size)
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            cache_key = f"{func.__module__}.{func.__name__}:{args}:{frozenset(kwargs.items())}"
            
            result = await cache.get_async(cache_key)
            if result is not None:
                return result
            
            result = await func(*args, **kwargs)
            await cache.set_async(cache_key, result, ttl)
            return result
        
        wrapper.cache = cache
        wrapper.clear_cache = cache._cache.clear
        wrapper.cache_stats = cache.stats
        
        return wrapper
    return decorator


@dataclass
class PerformanceMetrics:
    """Performance metrics snapshot."""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_mb: float = 0.0
    disk_io_read_mb: float = 0.0
    disk_io_write_mb: float = 0.0
    network_sent_mb: float = 0.0
    network_recv_mb: float = 0.0
    thread_count: int = 0
    process_count: int = 0
    load_avg: tuple = (0.0, 0.0, 0.0)


class PerformanceMonitor:
    """System performance monitoring."""
    
    def __init__(self, interval: float = 5.0):
        self.interval = interval
        self._running = False
        self._thread: threading.Thread | None = None
        self._metrics_history: list[PerformanceMetrics] = []
        self._max_history = 1000
        self._lock = threading.Lock()
        self._last_disk_io = psutil.disk_io_counters()
        self._last_net_io = psutil.net_io_counters()
    
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("Performance monitor started")
    
    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("Performance monitor stopped")
    
    def _monitor_loop(self) -> None:
        while self._running:
            try:
                self._collect_metrics()
            except Exception as e:
                logger.error(f"Metrics collection failed: {e}")
            time.sleep(self.interval)
    
    def _collect_metrics(self) -> None:
        process = psutil.Process()
        
        # CPU
        cpu_percent = process.cpu_percent()
        
        # Memory
        mem_info = process.memory_info()
        memory_mb = mem_info.rss / (1024 * 1024)
        memory_percent = process.memory_percent()
        
        # Disk I/O
        disk_io = psutil.disk_io_counters()
        disk_read_mb = 0
        disk_write_mb = 0
        if self._last_disk_io and disk_io:
            disk_read_mb = (disk_io.read_bytes - self._last_disk_io.read_bytes) / (1024 * 1024)
            disk_write_mb = (disk_io.write_bytes - self._last_disk_io.write_bytes) / (1024 * 1024)
        self._last_disk_io = disk_io
        
        # Network I/O
        net_io = psutil.net_io_counters()
        net_sent_mb = 0
        net_recv_mb = 0
        if self._last_net_io and net_io:
            net_sent_mb = (net_io.bytes_sent - self._last_net_io.bytes_sent) / (1024 * 1024)
            net_recv_mb = (net_io.bytes_recv - self._last_net_io.bytes_recv) / (1024 * 1024)
        self._last_net_io = net_io
        
        # Threads and processes
        thread_count = process.num_threads()
        process_count = len(psutil.pids())
        
        # Load average
        try:
            load_avg = os.getloadavg()
        except Exception:
            load_avg = (0.0, 0.0, 0.0)
        
        metrics = PerformanceMetrics(
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            memory_mb=memory_mb,
            disk_io_read_mb=disk_read_mb,
            disk_io_write_mb=disk_write_mb,
            network_sent_mb=net_sent_mb,
            network_recv_mb=net_recv_mb,
            thread_count=thread_count,
            process_count=process_count,
            load_avg=load_avg,
        )
        
        with self._lock:
            self._metrics_history.append(metrics)
            if len(self._metrics_history) > self._max_history:
                self._metrics_history = self._metrics_history[-self._max_history:]
    
    def get_current(self) -> PerformanceMetrics | None:
        with self._lock:
            return self._metrics_history[-1] if self._metrics_history else None
    
    def get_history(self, minutes: int = 60) -> list[PerformanceMetrics]:
        with self._lock:
            cutoff = datetime.now() - timedelta(minutes=minutes)
            cutoff_ts = cutoff.timestamp()
            return [
                m for m in self._metrics_history
                if datetime.fromisoformat(m.timestamp).timestamp() > cutoff_ts
            ]
    
    def get_summary(self, minutes: int = 60) -> dict[str, Any]:
        history = self.get_history(minutes)
        if not history:
            return {}
        
        return {
            "avg_cpu": sum(m.cpu_percent for m in history) / len(history),
            "max_cpu": max(m.cpu_percent for m in history),
            "avg_memory_mb": sum(m.memory_mb for m in history) / len(history),
            "max_memory_mb": max(m.memory_mb for m in history),
            "avg_threads": sum(m.thread_count for m in history) / len(history),
            "total_disk_read_mb": sum(m.disk_io_read_mb for m in history),
            "total_disk_write_mb": sum(m.disk_io_write_mb for m in history),
            "total_net_sent_mb": sum(m.network_sent_mb for m in history),
            "total_net_recv_mb": sum(m.network_recv_mb for m in history),
            "samples": len(history),
        }


class QueryOptimizer:
    """Database query optimization hints."""
    
    @staticmethod
    def analyze_query(query: str) -> dict[str, Any]:
        """Analyze SQL query for optimization opportunities."""
        issues = []
        suggestions = []
        
        query_upper = query.upper()
        
        # Check for SELECT *
        if "SELECT *" in query_upper:
            issues.append("SELECT * used")
            suggestions.append("Specify column names instead of SELECT *")
        
        # Check for missing WHERE - but allow if it has LIMIT
        if "SELECT" in query_upper and "WHERE" not in query_upper and "LIMIT" not in query_upper:
            issues.append("Missing WHERE clause")
            suggestions.append("Add WHERE clause to limit rows")
        
        # Check for missing indexes hint
        if "JOIN" in query_upper and "INDEX" not in query_upper:
            suggestions.append("Consider adding indexes on JOIN columns")
        
        # Check for subqueries
        if query_upper.count("SELECT") > 1:
            suggestions.append("Consider replacing subqueries with JOINs")
        
        # Check for ORDER BY without LIMIT
        if "ORDER BY" in query_upper and "LIMIT" not in query_upper:
            suggestions.append("Add LIMIT to ORDER BY queries")
        
        # Complexity: low if no issues, medium if 1-2 issues, high if 3+
        complexity = "low"
        if len(issues) >= 3:
            complexity = "high"
        elif len(issues) >= 1:
            complexity = "medium"
        
        # Override: simple query with just SELECT * and WHERE is still low
        if len(issues) == 1 and issues[0] == "SELECT * used" and "WHERE" in query_upper:
            # Count JOINs - if multiple JOINs, it's not simple
            join_count = query_upper.count("JOIN")
            if join_count <= 1:
                complexity = "low"
        
        # Also consider suggestions count for complexity (many suggestions = complex)
        if complexity == "low" and len(suggestions) >= 3:
            complexity = "medium"
        
        return {
            "issues": issues,
            "suggestions": suggestions,
            "complexity": complexity,
        }
    
    @staticmethod
    def suggest_indexes(query: str) -> list[str]:
        """Suggest indexes based on query patterns."""
        import re
        suggestions = []
        
        # Find WHERE columns (including table.column format)
        where_match = re.search(r'WHERE\s+(.+?)(?:\s+(?:ORDER|GROUP|LIMIT)|$)', query, re.IGNORECASE)
        if where_match:
            where_clause = where_match.group(1)
            # Extract column names including table.column format (with or without operator)
            cols = re.findall(r'(\w+)\.(\w+)', where_clause)
            for table, col in cols:
                suggestions.append(f"CREATE INDEX idx_{table}_{col} ON {table}({col}) -- {table}.{col}")
            # Also handle columns without table prefix
            cols_simple = re.findall(r'(?<!\.)(\w+)\s*[=<>!]', where_clause)
            for col in cols_simple:
                if col.upper() not in ('AND', 'OR', 'NOT', 'IN', 'LIKE', 'BETWEEN', 'IS', 'NULL'):
                    suggestions.append(f"CREATE INDEX idx_{col} ON table({col})")
        
        # Find JOIN columns
        join_matches = re.findall(r'JOIN\s+\w+\s+ON\s+(\w+)\.(\w+)\s*=\s*(\w+)\.(\w+)', query, re.IGNORECASE)
        for match in join_matches:
            suggestions.append(f"CREATE INDEX idx_{match[0]}_{match[1]} ON {match[0]}({match[1]}) -- {match[0]}.{match[1]}")
            suggestions.append(f"CREATE INDEX idx_{match[2]}_{match[3]} ON {match[2]}({match[3]}) -- {match[2]}.{match[3]}")
        
        return list(set(suggestions))


class ResourcePool:
    """Generic resource pool for connection/thread pooling."""
    
    def __init__(self, factory: Callable[[], Any], max_size: int = 10,
                 max_idle_time: float = 300):
        self.factory = factory
        self.max_size = max_size
        self.max_idle_time = max_idle_time
        self._pool: list[tuple[Any, float]] = []  # (resource, last_used)
        self._in_use: set = set()
        self._lock = threading.Lock()
        self._created = 0
    
    def acquire(self):
        """Acquire a resource (supports both context manager and direct use)."""
        resource = self._get_resource()
        return _AcquireContext(self, resource)
    
    def _get_resource(self) -> Any:
        with self._lock:
            now = time.time()
            # Clean up idle resources
            self._pool = [
                (r, t) for r, t in self._pool
                if now - t < self.max_idle_time
            ]
            
            if self._pool:
                resource, _ = self._pool.pop()
                self._in_use.add(id(resource))
                return resource
            
            if self._created < self.max_size:
                resource = self.factory()
                self._created += 1
                self._in_use.add(id(resource))
                return resource
            
            # Wait for resource (simplified)
            raise RuntimeError("Resource pool exhausted")
    
    def release(self, resource: Any) -> None:
        """Release a resource back to the pool."""
        # Handle both direct resource and _AcquireContext wrapper
        if isinstance(resource, _AcquireContext):
            resource = resource._resource
        with self._lock:
            resource_id = id(resource)
            if resource_id in self._in_use:
                self._in_use.remove(resource_id)
                self._pool.append((resource, time.time()))
    
    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "created": self._created,
                "in_use": len(self._in_use),
                "available": len(self._pool),
                "max_size": self.max_size,
            }


class _AcquireContext:
    """Context manager for resource acquisition that also works as direct resource holder."""
    
    def __init__(self, pool, resource):
        self.pool = pool
        self._resource = resource
    
    def __enter__(self):
        return self._resource
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._resource is not None:
            self.pool.release(self._resource)
            self._resource = None
    
    # Allow using the context manager object directly as the resource
    def __getattr__(self, name):
        if self._resource is not None:
            return getattr(self._resource, name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
    
    def __repr__(self):
        if self._resource is not None:
            return repr(self._resource)
        return f"<{type(self).__name__} (no resource)>"


class BatchProcessor:
    """Batch processing for throughput optimization."""
    
    def __init__(self, batch_size: int = 100, flush_interval: float = 1.0):
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._buffer: list[Any] = []
        self._lock = threading.Lock()
        self._last_flush = time.time()
        self._processor: Callable[[list[Any]], None] | None = None
        self._running = False
        self._thread: threading.Thread | None = None
    
    def set_processor(self, processor: Callable[[list[Any]], None]) -> None:
        self._processor = processor
    
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._thread.start()
    
    def stop(self) -> None:
        self._running = False
        self._flush()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
    
    def add(self, item: Any) -> None:
        with self._lock:
            self._buffer.append(item)
            if len(self._buffer) >= self.batch_size:
                self._flush_buffer()
    
    def _flush_loop(self) -> None:
        while self._running:
            time.sleep(self.flush_interval)
            self._flush()
    
    def _flush(self) -> None:
        with self._lock:
            self._flush_buffer()
    
    def _flush_buffer(self) -> None:
        if self._buffer and self._processor:
            batch = self._buffer[:]
            self._buffer.clear()
            try:
                self._processor(batch)
            except Exception as e:
                logger.error(f"Batch processing failed: {e}")
                # Re-queue failed items
                self._buffer = batch + self._buffer


# Global instances
_performance_monitor: PerformanceMonitor | None = None
_query_optimizer: QueryOptimizer = QueryOptimizer()


def get_performance_monitor(interval: float = 5.0) -> PerformanceMonitor:
    """Get global performance monitor."""
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor(interval)
    return _performance_monitor


def get_query_optimizer() -> QueryOptimizer:
    return _query_optimizer


def init_performance(monitor_interval: float = 5.0) -> PerformanceMonitor:
    """Initialize performance monitoring."""
    global _performance_monitor
    _performance_monitor = PerformanceMonitor(monitor_interval)
    return _performance_monitor