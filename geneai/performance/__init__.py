"""GeneAI Performance Optimization - Phase 5.10."""
from __future__ import annotations

from geneai.performance.core import (
    LRUCache,
    MultiLevelCache,
    AsyncCache,
    cached,
    async_cached,
    CacheEntry,
    CacheStrategy,
    PerformanceMonitor,
    PerformanceMetrics,
    QueryOptimizer,
    ResourcePool,
    BatchProcessor,
    get_performance_monitor,
    get_query_optimizer,
    init_performance,
)
from geneai.performance.ui import (
    render_performance_dashboard,
    render as render_performance,
)

__all__ = [
    # Core
    "LRUCache",
    "MultiLevelCache",
    "AsyncCache",
    "cached",
    "async_cached",
    "CacheEntry",
    "CacheStrategy",
    "PerformanceMonitor",
    "PerformanceMetrics",
    "QueryOptimizer",
    "ResourcePool",
    "BatchProcessor",
    "get_performance_monitor",
    "get_query_optimizer",
    "init_performance",
    # UI
    "render_performance_dashboard",
    "render_performance",
]

__version__ = "5.10.0"