"""Streamlit UI for Performance Optimization - Phase 5.10."""
from __future__ import annotations

import logging
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
from typing import Any

from geneai.performance.core import (
    LRUCache, MultiLevelCache, AsyncCache, cached, async_cached,
    PerformanceMonitor, PerformanceMetrics, QueryOptimizer,
    ResourcePool, BatchProcessor, get_performance_monitor,
    get_query_optimizer, init_performance
)

logger = logging.getLogger(__name__)


def render_performance_dashboard():
    """Render the performance optimization dashboard."""
    st.title("⚡ GeneAI Performance Optimization")
    st.caption("Caching, monitoring, query optimization, and resource pooling")
    
    # Initialize performance monitor
    if "perf_monitor" not in st.session_state:
        st.session_state.perf_monitor = init_performance(5.0)
        st.session_state.perf_monitor.start()
    
    if "query_optimizer" not in st.session_state:
        st.session_state.query_optimizer = get_query_optimizer()
    
    monitor: PerformanceMonitor = st.session_state.perf_monitor
    optimizer: QueryOptimizer = st.session_state.query_optimizer
    
    # Sidebar
    with st.sidebar:
        st.header("Performance Status")
        
        # Current metrics
        current = monitor.get_current()
        if current:
            st.metric("CPU", f"{current.cpu_percent:.1f}%")
            st.metric("Memory", f"{current.memory_mb:.1f} MB")
            st.metric("Threads", current.thread_count)
        
        st.divider()
        
        # Cache management
        st.subheader("Cache Management")
        
        if "lru_cache" not in st.session_state:
            st.session_state.lru_cache = LRUCache(max_size=100, default_ttl=300)
        
        cache = st.session_state.lru_cache
        stats = cache.stats()
        
        st.metric("Cache Size", f"{stats['size']}/{stats['max_size']}")
        st.metric("Hit Rate", f"{stats['hit_rate']:.1%}")
        st.metric("Hits", stats['hits'])
        st.metric("Misses", stats['misses'])
        
        if st.button("🧹 Cleanup Expired", use_container_width=True):
            cleaned = cache.cleanup_expired()
            st.success(f"Cleaned {cleaned} expired entries")
        
        if st.button("🗑️ Clear Cache", use_container_width=True):
            cache.clear()
            st.success("Cache cleared")
        
        st.divider()
        
        # Monitoring controls
        st.subheader("Monitoring")
        if st.button("📊 Refresh Metrics", use_container_width=True):
            st.rerun()
        
        history_minutes = st.selectbox("History Window", [5, 15, 30, 60, 120], index=3)
    
    # Main tabs
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 System Metrics", "💾 Caching", "🔍 Query Optimizer", 
        "🏊 Resource Pools", "⚙️ Batch Processing", "📈 Benchmarks"
    ])
    
    with tab1:
        render_metrics_tab(monitor, history_minutes)
    
    with tab2:
        render_caching_tab()
    
    with tab3:
        render_query_optimizer_tab(optimizer)
    
    with tab4:
        render_resource_pools_tab()
    
    with tab5:
        render_batch_processing_tab()
    
    with tab6:
        render_benchmarks_tab()


def render_metrics_tab(monitor: PerformanceMonitor, history_minutes: int):
    """Render system metrics tab."""
    st.subheader("System Performance Metrics")
    
    # Current snapshot
    current = monitor.get_current()
    if current:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("CPU Usage", f"{current.cpu_percent:.1f}%", 
                    delta=f"{current.load_avg[0]:.2f} load")
        col2.metric("Memory", f"{current.memory_mb:.1f} MB",
                    delta=f"{current.memory_percent:.1f}%")
        col3.metric("Threads", current.thread_count)
        col4.metric("Processes", current.process_count)
    
    st.divider()
    
    # Historical charts
    history = monitor.get_history(history_minutes)
    
    if history:
        df = pd.DataFrame([
            {
                "Time": datetime.fromisoformat(m.timestamp),
                "CPU %": m.cpu_percent,
                "Memory (MB)": m.memory_mb,
                "Memory %": m.memory_percent,
                "Threads": m.thread_count,
                "Disk Read (MB/s)": m.disk_io_read_mb,
                "Disk Write (MB/s)": m.disk_io_write_mb,
                "Net Sent (MB/s)": m.network_sent_mb,
                "Net Recv (MB/s)": m.network_recv_mb,
                "Load 1m": m.load_avg[0],
                "Load 5m": m.load_avg[1],
                "Load 15m": m.load_avg[2],
            }
            for m in history
        ])
        
        # CPU Chart
        st.write("### CPU Usage")
        fig = px.line(df, x="Time", y=["CPU %", "Load 1m", "Load 5m", "Load 15m"],
                      title="CPU Utilization")
        st.plotly_chart(fig, use_container_width=True)
        
        # Memory Chart
        st.write("### Memory Usage")
        fig = px.line(df, x="Time", y=["Memory (MB)", "Memory %"],
                      title="Memory Utilization")
        st.plotly_chart(fig, use_container_width=True)
        
        # I/O Chart
        st.write("### I/O Activity")
        fig = px.line(df, x="Time", y=["Disk Read (MB/s)", "Disk Write (MB/s)",
                                       "Net Sent (MB/s)", "Net Recv (MB/s)"],
                      title="I/O Throughput")
        st.plotly_chart(fig, use_container_width=True)
        
        # Summary stats
        st.write("### Summary Statistics")
        summary = monitor.get_summary(history_minutes)
        if summary:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Avg CPU", f"{summary['avg_cpu']:.1f}%")
            col2.metric("Max CPU", f"{summary['max_cpu']:.1f}%")
            col3.metric("Avg Memory", f"{summary['avg_memory_mb']:.1f} MB")
            col4.metric("Max Memory", f"{summary['max_memory_mb']:.1f} MB")
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Disk Read", f"{summary['total_disk_read_mb']:.1f} MB")
            col2.metric("Disk Write", f"{summary['total_disk_write_mb']:.1f} MB")
            col3.metric("Net Sent", f"{summary['total_net_sent_mb']:.1f} MB")
            col4.metric("Net Recv", f"{summary['total_net_recv_mb']:.1f} MB")
    else:
        st.info("Collecting metrics... Please wait.")
    
    # Export
    st.divider()
    if st.button("📥 Export Metrics CSV"):
        if history:
            df = pd.DataFrame([m.__dict__ for m in history])
            st.download_button(
                "Download",
                df.to_csv(index=False),
                f"metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                "text/csv",
            )


def render_caching_tab():
    """Render caching tab."""
    st.subheader("Caching Strategies")
    
    st.markdown("""
    GeneAI provides multiple caching layers for optimal performance:
    - **L1 Cache**: In-memory LRU with TTL support
    - **L2 Cache**: Persistent disk cache (MultiLevelCache)
    - **Async Cache**: Thread-safe async-compatible caching
    - **Function Caching**: Decorators for automatic memoization
    """)
    
    st.divider()
    
    # LRU Cache Demo
    st.write("### LRU Cache Demo")
    
    if "demo_cache" not in st.session_state:
        st.session_state.demo_cache = LRUCache(max_size=10, default_ttl=60)
    
    cache = st.session_state.demo_cache
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Set Values**")
        key = st.text_input("Key", "gene:TP53")
        value = st.text_area("Value", '{"symbol": "TP53", "name": "Tumor Protein P53"}')
        ttl = st.number_input("TTL (seconds)", 0, 3600, 60)
        
        if st.button("Set in Cache"):
            try:
                import json
                cache.set(key, json.loads(value), ttl=ttl if ttl > 0 else None)
                st.success(f"Cached: {key}")
            except Exception as e:
                st.error(f"Error: {e}")
    
    with col2:
        st.write("**Get Values**")
        get_key = st.text_input("Key to Retrieve", "gene:TP53")
        
        if st.button("Get from Cache"):
            result = cache.get(get_key)
            if result is not None:
                st.success("Cache HIT!")
                st.json(result)
            else:
                st.error("Cache MISS")
    
    # Cache stats
    stats = cache.stats()
    st.write("### Cache Statistics")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Size", f"{stats['size']}/{stats['max_size']}")
    col2.metric("Hit Rate", f"{stats['hit_rate']:.1%}")
    col3.metric("Hits", stats['hits'])
    col4.metric("Misses", stats['misses'])
    
    st.divider()
    
    # Function caching demo
    st.write("### Function Caching (@cached decorator)")
    
    @cached(ttl=30, max_size=50)
    def expensive_computation(gene: str, threshold: float = 0.8) -> dict:
        """Simulate expensive computation."""
        import time
        time.sleep(1)  # Simulate work
        return {
            "gene": gene,
            "threshold": threshold,
            "result": f"Analysis complete for {gene}",
            "computed_at": datetime.now().isoformat(),
        }
    
    col1, col2 = st.columns(2)
    with col1:
        gene = st.text_input("Gene", "TP53")
        threshold = st.slider("Threshold", 0.0, 1.0, 0.8)
    
    with col2:
        if st.button("Run Computation (Cached)"):
            start = time.time()
            result = expensive_computation(gene, threshold)
            elapsed = time.time() - start
            
            # Check if cached
            stats = expensive_computation.cache.stats()
            cached_before = stats['hits']
            
            # Run again
            result2 = expensive_computation(gene, threshold)
            stats2 = expensive_computation.cache.stats()
            
            if stats2['hits'] > cached_before:
                st.success(f"✅ Cached! (took {time.time() - start:.3f}s)")
            else:
                st.info(f"🔄 Computed (took {time.time() - start:.3f}s)")
            
            st.json(result)
            st.json(expensive_computation.cache.stats())
    
    st.divider()
    
    # Multi-level cache
    st.write("### Multi-Level Cache")
    st.info("L1 (Memory) + L2 (Disk) for persistence across restarts")


def render_query_optimizer_tab(optimizer: QueryOptimizer):
    """Render query optimizer tab."""
    st.subheader("SQL Query Optimizer")
    
    st.markdown("""
    Analyze SQL queries for performance issues and get optimization suggestions.
    """)
    
    # Query input
    query = st.text_area(
        "SQL Query",
        """SELECT * FROM genes 
JOIN diseases ON genes.id = diseases.gene_id 
WHERE genes.symbol = 'TP53' 
ORDER BY diseases.score DESC""",
        height=150
    )
    
    if st.button("Analyze Query", type="primary"):
        analysis = optimizer.analyze_query(query)
        indexes = optimizer.suggest_indexes(query)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("### Issues Found")
            if analysis["issues"]:
                for issue in analysis["issues"]:
                    st.error(f"⚠️ {issue}")
            else:
                st.success("No major issues found")
            
            st.write("### Suggestions")
            for suggestion in analysis["suggestions"]:
                st.info(f"💡 {suggestion}")
            
            st.write(f"**Complexity**: {analysis['complexity'].upper()}")
        
        with col2:
            st.write("### Suggested Indexes")
            if indexes:
                for idx in indexes:
                    st.code(idx, language="sql")
            else:
                st.info("No specific index suggestions")
    
    st.divider()
    
    # Common query patterns
    st.write("### Common Optimization Patterns")
    
    patterns = [
        ("❌ SELECT *", "✅ SELECT column1, column2", "Avoid SELECT *"),
        ("❌ No WHERE clause", "✅ WHERE condition", "Always filter"),
        ("❌ Subquery in WHERE", "✅ JOIN instead", "Prefer JOINs"),
        ("❌ ORDER BY without LIMIT", "✅ ORDER BY ... LIMIT 100", "Limit results"),
        ("❌ No indexes on JOIN cols", "✅ CREATE INDEX ON table(col)", "Index JOIN columns"),
        ("❌ Functions in WHERE", "✅ Avoid UPPER(col) = 'X'", "Sargable queries"),
    ]
    
    for bad, good, desc in patterns:
        col1, col2, col3 = st.columns([2, 2, 3])
        with col1:
            st.error(bad)
        with col2:
            st.success(good)
        with col3:
            st.caption(desc)


def render_resource_pools_tab():
    """Render resource pools tab."""
    st.subheader("Resource Pooling")
    
    st.markdown("""
    Reuse expensive resources (database connections, threads, processes) 
    to reduce allocation overhead.
    """)
    
    st.divider()
    
    # Connection pool demo
    st.write("### Connection Pool Demo")
    
    if "conn_pool" not in st.session_state:
        def create_connection():
            return {"id": id(object()), "created": time.time(), "active": True}
        
        st.session_state.conn_pool = ResourcePool(
            factory=create_connection,
            max_size=5,
            max_idle_time=60,
        )
    
    pool = st.session_state.conn_pool
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Pool Stats**")
        stats = pool.stats()
        st.json(stats)
    
    with col2:
        if st.button("Acquire Connection"):
            try:
                with pool.acquire() as conn:
                    st.success(f"Got connection: {conn}")
                    time.sleep(0.5)  # Simulate work
            except Exception as e:
                st.error(f"Pool exhausted: {e}")
        
        if st.button("Simulate Load (10 requests)"):
            import threading
            results = {"success": 0, "failed": 0}
            
            def worker():
                try:
                    with pool.acquire() as conn:
                        time.sleep(0.1)
                        results["success"] += 1
                except Exception:
                    results["failed"] += 1
            
            threads = [threading.Thread(target=worker) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            
            st.success(f"Completed: {results['success']} success, {results['failed']} failed")
    
    st.divider()
    
    # Thread pool
    st.write("### Thread/Process Pool")
    
    with st.form("thread_pool_form"):
        st.write("**Parallel Processing**")
        num_tasks = st.number_input("Number of Tasks", 1, 100, 10)
        max_workers = st.number_input("Max Workers", 1, 16, 4)
        use_process = st.checkbox("Use Process Pool (CPU-bound)")
        
        if st.form_submit_button("Run Parallel Tasks"):
            start = time.time()
            
            def cpu_task(n):
                # Simulate CPU work
                total = sum(i * i for i in range(10000))
                return n * total
            
            if use_process:
                with ProcessPoolExecutor(max_workers=max_workers) as executor:
                    results = list(executor.map(cpu_task, range(num_tasks)))
            else:
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    results = list(executor.map(cpu_task, range(num_tasks)))
            
            elapsed = time.time() - start
            st.success(f"Completed {num_tasks} tasks in {elapsed:.2f}s with {max_workers} workers")
            st.write(f"Results: {results[:5]}...")


def render_batch_processing_tab():
    """Render batch processing tab."""
    st.subheader("Batch Processing")
    
    st.markdown("""
    Accumulate items and process in batches for better throughput.
    """)
    
    if "batch_processor" not in st.session_state:
        def process_batch(batch):
            st.session_state.batch_results.append({
                "batch_size": len(batch),
                "items": batch,
                "processed_at": datetime.now().isoformat(),
            })
        
        st.session_state.batch_processor = BatchProcessor(
            batch_size=5,
            flush_interval=2.0,
        )
        st.session_state.batch_processor.set_processor(process_batch)
        st.session_state.batch_results = []
    
    processor = st.session_state.batch_processor
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Add Items**")
        item = st.text_input("Item", f"item_{len(st.session_state.batch_results) + 1}")
        
        if st.button("Add to Batch"):
            processor.add(item)
            st.success(f"Added: {item}")
        
        if st.button("Flush Now"):
            processor._flush()
            st.success("Batch flushed")
    
    with col2:
        st.write("**Batch Results**")
        if st.session_state.batch_results:
            for i, result in enumerate(st.session_state.batch_results[-5:]):
                st.write(f"Batch {len(st.session_state.batch_results) - 4 + i}: {result['batch_size']} items")
        else:
            st.info("No batches processed yet")
    
    # Auto-flush demo
    st.divider()
    st.write("### Auto-Flush Demo")
    
    if st.button("Start Auto-Add (5 items/sec for 10s)"):
        processor.start()
        import threading
        
        def auto_add():
            for i in range(50):
                if not processor._running:
                    break
                processor.add(f"auto_item_{i}")
                time.sleep(0.2)
            processor.stop()
        
        thread = threading.Thread(target=auto_add, daemon=True)
        thread.start()
        st.success("Auto-add started! Check results above.")


def render_benchmarks_tab():
    """Render benchmarks tab."""
    st.subheader("Performance Benchmarks")
    
    st.markdown("""
    Run standardized benchmarks to measure system performance.
    """)
    
    # Benchmark selection
    benchmarks = {
        "CPU": "cpu_benchmark",
        "Memory": "memory_benchmark",
        "Disk I/O": "disk_benchmark",
        "JSON Serialization": "json_benchmark",
        "Cache Operations": "cache_benchmark",
        "Database Queries": "db_benchmark",
    }
    
    selected = st.multiselect(
        "Select Benchmarks",
        list(benchmarks.keys()),
        default=["CPU", "Cache Operations"]
    )
    
    if st.button("Run Benchmarks", type="primary"):
        results = {}
        
        for bench_name in selected:
            with st.spinner(f"Running {bench_name}..."):
                if bench_name == "CPU":
                    results[bench_name] = run_cpu_benchmark()
                elif bench_name == "Memory":
                    results[bench_name] = run_memory_benchmark()
                elif bench_name == "Cache Operations":
                    results[bench_name] = run_cache_benchmark()
                elif bench_name == "JSON Serialization":
                    results[bench_name] = run_json_benchmark()
                elif bench_name == "Disk I/O":
                    results[bench_name] = run_disk_benchmark()
                elif bench_name == "Database Queries":
                    results[bench_name] = run_db_benchmark()
        
        # Display results
        st.write("### Benchmark Results")
        
        for name, result in results.items():
            with st.expander(f"📊 {name}", expanded=True):
                if "error" in result:
                    st.error(result["error"])
                else:
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Duration", f"{result.get('duration', 0):.3f}s")
                    col2.metric("Operations", result.get('operations', 0))
                    col3.metric("Ops/sec", f"{result.get('ops_per_sec', 0):,.0f}")
                    
                    if "details" in result:
                        st.json(result["details"])
    
    st.divider()
    
    # Continuous benchmarking
    st.write("### Continuous Benchmarking")
    st.info("Schedule regular benchmarks to track performance over time")


def run_cpu_benchmark() -> dict[str, Any]:
    """Run CPU benchmark."""
    import math
    start = time.time()
    operations = 0
    
    # CPU-intensive work
    for i in range(100000):
        math.sqrt(i) * math.sin(i) * math.cos(i)
        operations += 1
    
    duration = time.time() - start
    return {
        "duration": duration,
        "operations": operations,
        "ops_per_sec": operations / duration,
        "details": {"test": "math operations"},
    }


def run_memory_benchmark() -> dict[str, Any]:
    """Run memory benchmark."""
    start = time.time()
    operations = 0
    
    # Memory allocation
    data = []
    for i in range(10000):
        data.append("x" * 1000)
        operations += 1
    
    # Access
    total = sum(len(d) for d in data)
    operations += 10000
    
    duration = time.time() - start
    return {
        "duration": duration,
        "operations": operations,
        "ops_per_sec": operations / duration,
        "details": {"allocated_mb": len(data) * 1000 / (1024*1024)},
    }


def run_cache_benchmark() -> dict[str, Any]:
    """Run cache benchmark."""
    cache = LRUCache(max_size=10000)
    operations = 100000
    
    # Write benchmark
    start = time.time()
    for i in range(operations):
        cache.set(f"key_{i}", f"value_{i}")
    write_time = time.time() - start
    
    # Read benchmark
    start = time.time()
    hits = 0
    for i in range(operations):
        if cache.get(f"key_{i}") is not None:
            hits += 1
    read_time = time.time() - start
    
    return {
        "duration": write_time + read_time,
        "operations": operations * 2,
        "ops_per_sec": (operations * 2) / (write_time + read_time),
        "details": {
            "write_time": write_time,
            "read_time": read_time,
            "hit_rate": hits / operations,
        },
    }


def run_json_benchmark() -> dict[str, Any]:
    """Run JSON serialization benchmark."""
    import json
    data = {"key": "value", "numbers": list(range(100)), "nested": {"a": 1, "b": 2}} * 10
    operations = 50000
    
    # Serialize
    start = time.time()
    for _ in range(operations):
        json.dumps(data)
    serialize_time = time.time() - start
    
    # Deserialize
    serialized = json.dumps(data)
    start = time.time()
    for _ in range(operations):
        json.loads(serialized)
    deserialize_time = time.time() - start
    
    return {
        "duration": serialize_time + deserialize_time,
        "operations": operations * 2,
        "ops_per_sec": (operations * 2) / (serialize_time + deserialize_time),
        "details": {
            "serialize_time": serialize_time,
            "deserialize_time": deserialize_time,
        },
    }


def run_disk_benchmark() -> dict[str, Any]:
    """Run disk I/O benchmark."""
    import tempfile
    import os
    
    operations = 1000
    block_size = 1024 * 1024  # 1MB
    data = os.urandom(block_size)
    
    with tempfile.NamedTemporaryFile(delete=False) as f:
        temp_path = f.name
    
    try:
        # Write
        start = time.time()
        for _ in range(operations):
            with open(temp_path, 'wb') as f:
                f.write(data)
        write_time = time.time() - start
        
        # Read
        start = time.time()
        for _ in range(operations):
            with open(temp_path, 'rb') as f:
                f.read()
        read_time = time.time() - start
        
        return {
            "duration": write_time + read_time,
            "operations": operations * 2,
            "ops_per_sec": (operations * 2) / (write_time + read_time),
            "details": {
                "write_time": write_time,
                "read_time": read_time,
                "block_size_mb": block_size / (1024*1024),
            },
        }
    finally:
        os.unlink(temp_path)


def run_db_benchmark() -> dict[str, Any]:
    """Run database benchmark (SQLite in-memory)."""
    import sqlite3
    
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, data TEXT)")
    operations = 10000
    
    # Insert
    start = time.time()
    for i in range(operations):
        conn.execute("INSERT INTO test (data) VALUES (?)", (f"data_{i}",))
    conn.commit()
    insert_time = time.time() - start
    
    # Select
    start = time.time()
    for i in range(0, operations, 100):
        conn.execute("SELECT * FROM test WHERE id BETWEEN ? AND ?", (i, i+99)).fetchall()
    select_time = time.time() - start
    
    return {
        "duration": insert_time + select_time,
        "operations": operations + operations // 100,
        "ops_per_sec": (operations + operations // 100) / (insert_time + select_time),
        "details": {
            "insert_time": insert_time,
            "select_time": select_time,
        },
    }


def render():
    """Main render function."""
    render_performance_dashboard()


if __name__ == "__main__":
    render()