"""
Performance monitoring utilities for the agent system.

This module provides decorators and utilities for tracking execution times,
success rates, and resource usage across key operations.
"""

import time
import functools
import asyncio
import atexit
import threading
from typing import Dict, List, Optional, Callable, TypeVar, ParamSpec, Any
from dataclasses import dataclass, field
from collections import defaultdict, deque
from contextlib import asynccontextmanager, contextmanager
from log import get_structured_logger

logger = get_structured_logger(__name__)

P = ParamSpec('P')
T = TypeVar('T')


@dataclass
class PerformanceMetric:
    """Individual performance metric data."""
    operation: str
    duration_ms: float
    success: bool
    timestamp: float
    context: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class OperationStats:
    """Aggregated statistics for an operation."""
    operation: str
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_duration_ms: float = 0.0
    min_duration_ms: float = float('inf')
    max_duration_ms: float = 0.0
    avg_duration_ms: float = 0.0
    success_rate: float = 0.0
    recent_durations: deque = field(default_factory=lambda: deque(maxlen=100))
    
    def update(self, metric: PerformanceMetric):
        """Update stats with a new metric."""
        self.total_calls += 1
        self.total_duration_ms += metric.duration_ms
        self.recent_durations.append(metric.duration_ms)
        
        if metric.success:
            self.successful_calls += 1
        else:
            self.failed_calls += 1
        
        self.min_duration_ms = min(self.min_duration_ms, metric.duration_ms)
        self.max_duration_ms = max(self.max_duration_ms, metric.duration_ms)
        self.avg_duration_ms = self.total_duration_ms / self.total_calls
        self.success_rate = self.successful_calls / self.total_calls
    
    def get_percentile(self, percentile: float) -> float:
        """Get percentile duration from recent measurements."""
        if not self.recent_durations:
            return 0.0
        
        sorted_durations = sorted(self.recent_durations)
        index = int(len(sorted_durations) * percentile / 100)
        return sorted_durations[min(index, len(sorted_durations) - 1)]


class PerformanceMonitor:
    """Central performance monitoring system."""
    
    def __init__(self, max_metrics: int = 10000):
        self.max_metrics = max_metrics
        self.metrics: List[PerformanceMetric] = []
        self.stats: Dict[str, OperationStats] = defaultdict(lambda: OperationStats(""))
        self._lock = threading.Lock()
        self.enabled = True
    
    def record_metric(self, metric: PerformanceMetric):
        """Record a performance metric."""
        if not self.enabled:
            return
        
        with self._lock:
            self.metrics.append(metric)
            
            # Maintain max metrics limit
            if len(self.metrics) > self.max_metrics:
                self.metrics = self.metrics[-self.max_metrics:]
            
            # Update operation stats
            if metric.operation not in self.stats:
                self.stats[metric.operation] = OperationStats(metric.operation)
            
            self.stats[metric.operation].update(metric)
        
        # Log performance metric
        logger.log_performance(
            metric.operation,
            metric.duration_ms,
            success=metric.success,
            context=metric.context,
            error=metric.error
        )
    
    def get_stats(self, operation: Optional[str] = None) -> Dict[str, OperationStats]:
        """Get performance statistics."""
        with self._lock:
            if operation:
                return {operation: self.stats.get(operation, OperationStats(operation))}
            return dict(self.stats)
    
    def get_recent_metrics(self, operation: Optional[str] = None, limit: int = 100) -> List[PerformanceMetric]:
        """Get recent metrics, optionally filtered by operation."""
        with self._lock:
            metrics = self.metrics[-limit:] if not operation else [
                m for m in self.metrics[-limit:] if m.operation == operation
            ]
            return metrics
    
    def clear_metrics(self):
        """Clear all stored metrics and stats."""
        with self._lock:
            self.metrics.clear()
            self.stats.clear()
    
    def disable(self):
        """Disable performance monitoring."""
        self.enabled = False
    
    def enable(self):
        """Enable performance monitoring."""
        self.enabled = True
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of all performance data."""
        with self._lock:
            summary = {
                "total_operations": len(self.stats),
                "total_metrics": len(self.metrics),
                "operations": {}
            }
            
            for operation, stats in self.stats.items():
                summary["operations"][operation] = {
                    "total_calls": stats.total_calls,
                    "success_rate": f"{stats.success_rate:.2%}",
                    "avg_duration_ms": f"{stats.avg_duration_ms:.2f}",
                    "min_duration_ms": f"{stats.min_duration_ms:.2f}",
                    "max_duration_ms": f"{stats.max_duration_ms:.2f}",
                    "p50_duration_ms": f"{stats.get_percentile(50):.2f}",
                    "p95_duration_ms": f"{stats.get_percentile(95):.2f}",
                    "p99_duration_ms": f"{stats.get_percentile(99):.2f}",
                }
            
            return summary


# Global performance monitor instance
_monitor = PerformanceMonitor()


def get_monitor() -> PerformanceMonitor:
    """Get the global performance monitor instance."""
    return _monitor


def monitor_performance(
    operation: Optional[str] = None,
    include_args: bool = False,
    include_result: bool = False
):
    """
    Decorator to monitor function performance.
    
    Args:
        operation: Custom operation name (defaults to function name)
        include_args: Whether to include function arguments in context
        include_result: Whether to include return value in context
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        op_name = operation or f"{func.__module__}.{func.__name__}"
        
        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            start_time = time.time()
            success = True
            error = None
            result = None
            context = {}
            
            try:
                if include_args:
                    context["args"] = str(args)[:200]  # Truncate for logging
                    context["kwargs"] = str(kwargs)[:200]
                
                result = func(*args, **kwargs)
                
                if include_result:
                    context["result"] = str(result)[:200]
                
                return result
            except Exception as e:
                success = False
                error = str(e)
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                metric = PerformanceMetric(
                    operation=op_name,
                    duration_ms=duration_ms,
                    success=success,
                    timestamp=time.time(),
                    context=context,
                    error=error
                )
                _monitor.record_metric(metric)
        
        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            start_time = time.time()
            success = True
            error = None
            result = None
            context = {}
            
            try:
                if include_args:
                    context["args"] = str(args)[:200]  # Truncate for logging
                    context["kwargs"] = str(kwargs)[:200]
                
                result = await func(*args, **kwargs)
                
                if include_result:
                    context["result"] = str(result)[:200]
                
                return result
            except Exception as e:
                success = False
                error = str(e)
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                metric = PerformanceMetric(
                    operation=op_name,
                    duration_ms=duration_ms,
                    success=success,
                    timestamp=time.time(),
                    context=context,
                    error=error
                )
                _monitor.record_metric(metric)
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


@contextmanager
def performance_context(operation: str, **context):
    """Context manager for monitoring performance of code blocks."""
    start_time = time.time()
    success = True
    error = None
    
    try:
        yield
    except Exception as e:
        success = False
        error = str(e)
        raise
    finally:
        duration_ms = (time.time() - start_time) * 1000
        metric = PerformanceMetric(
            operation=operation,
            duration_ms=duration_ms,
            success=success,
            timestamp=time.time(),
            context=context,
            error=error
        )
        _monitor.record_metric(metric)


@asynccontextmanager
async def async_performance_context(operation: str, **context):
    """Async context manager for monitoring performance of code blocks."""
    start_time = time.time()
    success = True
    error = None
    
    try:
        yield
    except Exception as e:
        success = False
        error = str(e)
        raise
    finally:
        duration_ms = (time.time() - start_time) * 1000
        metric = PerformanceMetric(
            operation=operation,
            duration_ms=duration_ms,
            success=success,
            timestamp=time.time(),
            context=context,
            error=error
        )
        _monitor.record_metric(metric)


def log_performance_summary():
    """Log a summary of all performance metrics."""
    summary = _monitor.get_summary()
    logger.info("Performance Summary", **summary)


def reset_performance_metrics():
    """Reset all performance metrics."""
    _monitor.clear_metrics()
    logger.info("Performance metrics reset")


# Optional: Automatically log performance summary on module exit

def safe_log_performance_summary():
    """Safely log performance summary, handling closed file errors."""
    try:
        log_performance_summary()
    except (ValueError, OSError):
        # Ignore errors from closed files during shutdown
        pass

atexit.register(safe_log_performance_summary)
