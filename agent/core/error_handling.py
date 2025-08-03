"""
Enhanced error handling utilities for the agent system.

This module provides consistent error handling patterns, custom exceptions,
and utilities for error recovery and logging.
"""

import functools
import traceback
from typing import Any, Callable, TypeVar, ParamSpec, Optional, Union
from enum import Enum
import asyncio
from log import get_logger

logger = get_logger(__name__)

P = ParamSpec('P')
T = TypeVar('T')


class ErrorSeverity(Enum):
    """Error severity levels for categorizing exceptions."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AgentError(Exception):
    """Base exception class for agent-specific errors."""
    
    def __init__(
        self, 
        message: str, 
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        context: Optional[dict] = None,
        cause: Optional[Exception] = None
    ):
        super().__init__(message)
        self.message = message
        self.severity = severity
        self.context = context or {}
        self.cause = cause
        
    def to_dict(self) -> dict:
        """Convert error to dictionary for logging/serialization."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "severity": self.severity.value,
            "context": self.context,
            "cause": str(self.cause) if self.cause else None,
            "traceback": traceback.format_exc()
        }


class LLMError(AgentError):
    """Errors related to LLM operations."""
    pass


class WorkspaceError(AgentError):
    """Errors related to workspace operations."""
    pass


class ValidationError(AgentError):
    """Errors related to data validation."""
    pass


class ConfigurationError(AgentError):
    """Errors related to configuration issues."""
    pass


def with_error_handling(
    *,
    default_return: Any = None,
    reraise: bool = True,
    log_errors: bool = True,
    error_context: Optional[dict] = None
):
    """
    Decorator for consistent error handling across functions.
    
    Args:
        default_return: Value to return if an error occurs and reraise=False
        reraise: Whether to reraise the exception after logging
        log_errors: Whether to log errors
        error_context: Additional context to include in error logs
    """
    def decorator(func: Callable[P, T]) -> Callable[P, Union[T, Any]]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> Union[T, Any]:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if log_errors:
                    context = {
                        "function": func.__name__,
                        "args": str(args)[:200],  # Truncate for logging
                        "kwargs": str(kwargs)[:200],
                        **(error_context or {})
                    }
                    
                    if isinstance(e, AgentError):
                        logger.error(f"Agent error in {func.__name__}: {e.to_dict()}")
                    else:
                        logger.exception(f"Unexpected error in {func.__name__}: {str(e)}", extra=context)
                
                if reraise:
                    raise
                return default_return
        return wrapper
    return decorator


def with_async_error_handling(
    *,
    default_return: Any = None,
    reraise: bool = True,
    log_errors: bool = True,
    error_context: Optional[dict] = None
):
    """
    Async version of the error handling decorator.
    """
    def decorator(func: Callable[P, T]) -> Callable[P, Union[T, Any]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Union[T, Any]:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                if log_errors:
                    context = {
                        "function": func.__name__,
                        "args": str(args)[:200],  # Truncate for logging
                        "kwargs": str(kwargs)[:200],
                        **(error_context or {})
                    }
                    
                    if isinstance(e, AgentError):
                        logger.error(f"Agent error in {func.__name__}: {e.to_dict()}")
                    else:
                        logger.exception(f"Unexpected error in {func.__name__}: {str(e)}", extra=context)
                
                if reraise:
                    raise
                return default_return
        return wrapper
    return decorator


class ErrorRecovery:
    """Utility class for implementing error recovery strategies."""
    
    @staticmethod
    async def retry_with_backoff(
        func: Callable[[], T],
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0,
        exceptions: tuple = (Exception,)
    ) -> T:
        """
        Retry a function with exponential backoff.
        
        Args:
            func: Function to retry
            max_retries: Maximum number of retry attempts
            base_delay: Initial delay between retries
            max_delay: Maximum delay between retries
            backoff_factor: Factor to multiply delay by after each retry
            exceptions: Tuple of exceptions to catch and retry on
        """
        last_exception = None
        delay = base_delay
        
        for attempt in range(max_retries + 1):
            try:
                if asyncio.iscoroutinefunction(func):
                    return await func()
                else:
                    return func()
            except exceptions as e:
                last_exception = e
                
                if attempt == max_retries:
                    logger.error(f"Function {func.__name__} failed after {max_retries} retries")
                    break
                
                logger.warning(f"Attempt {attempt + 1} failed for {func.__name__}: {str(e)}. Retrying in {delay}s...")
                await asyncio.sleep(delay)
                delay = min(delay * backoff_factor, max_delay)
        
        raise last_exception
    
    @staticmethod
    def circuit_breaker(
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: type = Exception
    ):
        """
        Circuit breaker pattern implementation.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Time to wait before attempting recovery
            expected_exception: Exception type to count as failures
        """
        def decorator(func: Callable[P, T]) -> Callable[P, T]:
            func._failure_count = 0
            func._last_failure_time = 0
            func._circuit_open = False
            
            @functools.wraps(func)
            async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                import time
                
                # Check if circuit is open and if recovery timeout has passed
                if func._circuit_open:
                    if time.time() - func._last_failure_time < recovery_timeout:
                        raise AgentError(
                            f"Circuit breaker is open for {func.__name__}",
                            severity=ErrorSeverity.HIGH,
                            context={"failure_count": func._failure_count}
                        )
                    else:
                        # Try to close circuit
                        func._circuit_open = False
                        func._failure_count = 0
                
                try:
                    if asyncio.iscoroutinefunction(func):
                        result = await func(*args, **kwargs)
                    else:
                        result = func(*args, **kwargs)
                    
                    # Reset failure count on success
                    func._failure_count = 0
                    return result
                    
                except expected_exception as e:
                    func._failure_count += 1
                    func._last_failure_time = time.time()
                    
                    if func._failure_count >= failure_threshold:
                        func._circuit_open = True
                        logger.error(f"Circuit breaker opened for {func.__name__} after {failure_threshold} failures")
                    
                    raise
            
            return wrapper
        return decorator


def safe_execute(
    func: Callable[[], T],
    default: T,
    error_message: str = "Operation failed",
    log_level: str = "error"
) -> T:
    """
    Safely execute a function with a default fallback.
    
    Args:
        func: Function to execute
        default: Default value to return on error
        error_message: Message to log on error
        log_level: Logging level for errors
    """
    try:
        return func()
    except Exception as e:
        getattr(logger, log_level)(f"{error_message}: {str(e)}")
        return default


def validate_input(
    value: Any,
    validator: Callable[[Any], bool],
    error_message: str,
    severity: ErrorSeverity = ErrorSeverity.MEDIUM
) -> None:
    """
    Validate input with custom validator function.
    
    Args:
        value: Value to validate
        validator: Function that returns True if value is valid
        error_message: Error message if validation fails
        severity: Error severity level
    """
    if not validator(value):
        raise ValidationError(
            error_message,
            severity=severity,
            context={"value": str(value)[:100]}
        )

