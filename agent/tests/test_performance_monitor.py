"""
Tests for the performance monitoring system.
"""

import pytest
import asyncio
import time
from core.performance_monitor import (
    PerformanceMonitor, PerformanceMetric, monitor_performance,
    performance_context, async_performance_context, get_monitor
)


def test_performance_metric():
    """Test PerformanceMetric creation and properties."""
    metric = PerformanceMetric(
        operation="test_op",
        duration_ms=100.5,
        success=True,
        timestamp=time.time(),
        context={"key": "value"}
    )
    
    assert metric.operation == "test_op"
    assert metric.duration_ms == 100.5
    assert metric.success is True
    assert metric.context == {"key": "value"}


def test_performance_monitor():
    """Test basic PerformanceMonitor functionality."""
    monitor = PerformanceMonitor(max_metrics=10)
    
    # Test recording metrics
    metric1 = PerformanceMetric("op1", 50.0, True, time.time())
    metric2 = PerformanceMetric("op1", 75.0, True, time.time())
    metric3 = PerformanceMetric("op2", 100.0, False, time.time(), error="test error")
    
    monitor.record_metric(metric1)
    monitor.record_metric(metric2)
    monitor.record_metric(metric3)
    
    # Test stats
    stats = monitor.get_stats()
    assert "op1" in stats
    assert "op2" in stats
    
    op1_stats = stats["op1"]
    assert op1_stats.total_calls == 2
    assert op1_stats.successful_calls == 2
    assert op1_stats.failed_calls == 0
    assert op1_stats.success_rate == 1.0
    assert op1_stats.avg_duration_ms == 62.5
    
    op2_stats = stats["op2"]
    assert op2_stats.total_calls == 1
    assert op2_stats.successful_calls == 0
    assert op2_stats.failed_calls == 1
    assert op2_stats.success_rate == 0.0


def test_monitor_performance_decorator():
    """Test the monitor_performance decorator."""
    monitor = PerformanceMonitor()
    
    @monitor_performance(operation="test_function")
    def test_func(x, y):
        time.sleep(0.01)  # Small delay
        return x + y
    
    # Patch the global monitor temporarily
    import core.performance_monitor
    original_monitor = core.performance_monitor._monitor
    core.performance_monitor._monitor = monitor
    
    try:
        result = test_func(1, 2)
        assert result == 3
        
        stats = monitor.get_stats()
        assert "test_function" in stats
        assert stats["test_function"].total_calls == 1
        assert stats["test_function"].successful_calls == 1
        assert stats["test_function"].avg_duration_ms > 0
    finally:
        core.performance_monitor._monitor = original_monitor


@pytest.mark.asyncio
async def test_async_monitor_performance_decorator():
    """Test the monitor_performance decorator with async functions."""
    monitor = PerformanceMonitor()
    
    @monitor_performance(operation="test_async_function")
    async def test_async_func(x, y):
        await asyncio.sleep(0.01)  # Small delay
        return x * y
    
    # Patch the global monitor temporarily
    import core.performance_monitor
    original_monitor = core.performance_monitor._monitor
    core.performance_monitor._monitor = monitor
    
    try:
        result = await test_async_func(3, 4)
        assert result == 12
        
        stats = monitor.get_stats()
        assert "test_async_function" in stats
        assert stats["test_async_function"].total_calls == 1
        assert stats["test_async_function"].successful_calls == 1
        assert stats["test_async_function"].avg_duration_ms > 0
    finally:
        core.performance_monitor._monitor = original_monitor


def test_performance_context():
    """Test the performance_context context manager."""
    monitor = PerformanceMonitor()
    
    # Patch the global monitor temporarily
    import core.performance_monitor
    original_monitor = core.performance_monitor._monitor
    core.performance_monitor._monitor = monitor
    
    try:
        with performance_context("test_context", key="value"):
            time.sleep(0.01)
        
        stats = monitor.get_stats()
        assert "test_context" in stats
        assert stats["test_context"].total_calls == 1
        assert stats["test_context"].successful_calls == 1
    finally:
        core.performance_monitor._monitor = original_monitor


@pytest.mark.asyncio
async def test_async_performance_context():
    """Test the async_performance_context context manager."""
    monitor = PerformanceMonitor()
    
    # Patch the global monitor temporarily
    import core.performance_monitor
    original_monitor = core.performance_monitor._monitor
    core.performance_monitor._monitor = monitor
    
    try:
        async with async_performance_context("test_async_context", key="value"):
            await asyncio.sleep(0.01)
        
        stats = monitor.get_stats()
        assert "test_async_context" in stats
        assert stats["test_async_context"].total_calls == 1
        assert stats["test_async_context"].successful_calls == 1
    finally:
        core.performance_monitor._monitor = original_monitor


def test_monitor_disable_enable():
    """Test disabling and enabling the monitor."""
    monitor = PerformanceMonitor()
    
    # Test that metrics are recorded when enabled
    metric = PerformanceMetric("test", 100.0, True, time.time())
    monitor.record_metric(metric)
    assert len(monitor.metrics) == 1
    
    # Test that metrics are not recorded when disabled
    monitor.disable()
    metric2 = PerformanceMetric("test2", 200.0, True, time.time())
    monitor.record_metric(metric2)
    assert len(monitor.metrics) == 1  # Should still be 1
    
    # Test that metrics are recorded again when re-enabled
    monitor.enable()
    metric3 = PerformanceMetric("test3", 300.0, True, time.time())
    monitor.record_metric(metric3)
    assert len(monitor.metrics) == 2


def test_get_summary():
    """Test the get_summary method."""
    monitor = PerformanceMonitor()
    
    # Add some test metrics
    monitor.record_metric(PerformanceMetric("op1", 100.0, True, time.time()))
    monitor.record_metric(PerformanceMetric("op1", 200.0, True, time.time()))
    monitor.record_metric(PerformanceMetric("op2", 150.0, False, time.time(), error="test"))
    
    summary = monitor.get_summary()
    
    assert summary["total_operations"] == 2
    assert summary["total_metrics"] == 3
    assert "operations" in summary
    assert "op1" in summary["operations"]
    assert "op2" in summary["operations"]
    
    op1_summary = summary["operations"]["op1"]
    assert op1_summary["total_calls"] == 2
    assert op1_summary["success_rate"] == "100.00%"

