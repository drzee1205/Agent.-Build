"""
Global logging setup for the agent system.

Provides a centralized logging configuration used by various components
(Api, Core, TrpcAgent, LLM, Test Clients) as indicated in the architecture diagram.
"""
import logging
import logging.handlers
import logging.config
import ujson as json
import sentry_sdk
import os
import socket
from contextvars import ContextVar

# Configure root logger to avoid duplicate handlers
root_logger = logging.getLogger()
if root_logger.handlers:
    for handler in root_logger.handlers:
        root_logger.removeHandler(handler)

trace_id_var = ContextVar('trace_id', default=None)


def get_trace_id():
    return trace_id_var.get()


def set_trace_id(trace_id):
    if trace_id:
        trace_id_var.set(trace_id)

def clear_trace_id():
    trace_id_var.set(None)


def is_running_in_ecs() -> bool:
    return bool(os.getenv('ECS_CONTAINER_METADATA_URI') or
               os.getenv('AWS_EXECUTION_ENV', '').startswith('AWS_ECS'))


class TracedLogRecord(logging.LogRecord):
    def __init__(self, *args, trace_id: str = "unk", **kwargs, ):
        super().__init__(*args, **kwargs)
        self.trace_id = trace_id

class TraceLogFactory:
    def __call__(self, *args, **kwargs):
        record = TracedLogRecord(*args,trace_id=get_trace_id() or "unk",  **kwargs )
        return record

logging.setLogRecordFactory(TraceLogFactory())

class JsonFormatter(logging.Formatter):
    def __init__(self):
        super().__init__()
        self.hostname = socket.gethostname()

    def format(self, record: TracedLogRecord) -> str:  # type: ignore
        log_data = {
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'logger': record.name,
            'file': record.filename,
            'line': record.lineno,
            'message': record.getMessage(),
            'hostname': self.hostname,
            "trace_id": record.trace_id,
        }

        # Add exception info if available
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)

        # Add structured data from extra fields
        if hasattr(record, 'extra_data'):
            log_data.update(record.extra_data)
        
        # Add performance metrics if available
        if hasattr(record, 'duration'):
            log_data['duration_ms'] = record.duration
        
        # Add operation context if available
        if hasattr(record, 'operation'):
            log_data['operation'] = record.operation
        
        # Add error severity if available
        if hasattr(record, 'severity'):
            log_data['severity'] = record.severity

        return json.dumps(log_data)

# Standard text formatter
_TEXT_FORMATTER = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(name)s - %(trace_id)s - %(filename)s:%(lineno)d - %(message)s'
)

# Choose formatter based on environment
_FORMATTER = JsonFormatter() if is_running_in_ecs() else _TEXT_FORMATTER


def _init_logging():
    handlers = {}

    # Console handler
    console = logging.StreamHandler()
    console.setFormatter(_FORMATTER)
    handlers['console'] = console

    # Configure the root logger with these handlers
    for handler in handlers.values():
        if handler is not None:
            root_logger.addHandler(handler)

    root_logger.setLevel(logging.DEBUG if os.getenv('DEBUG_LOG') else logging.INFO)

    # Set log levels for noisy loggers
    for package in ['urllib3', 'httpx', 'google_genai.models', "anthropic._base_client"]:
        logging.getLogger(package).setLevel(logging.WARNING)

    return handlers

# Initialize logging once at module import
_init_logging()


class StructuredLogger:
    """Enhanced logger with structured logging capabilities."""
    
    def __init__(self, logger: logging.Logger):
        self._logger = logger
    
    def _log_with_extra(self, level: int, msg: str, **kwargs):
        """Log with structured extra data."""
        extra = {}
        if kwargs:
            extra['extra_data'] = kwargs
        self._logger.log(level, msg, extra=extra)
    
    def debug(self, msg: str, **kwargs):
        self._log_with_extra(logging.DEBUG, msg, **kwargs)
    
    def info(self, msg: str, **kwargs):
        self._log_with_extra(logging.INFO, msg, **kwargs)
    
    def warning(self, msg: str, **kwargs):
        self._log_with_extra(logging.WARNING, msg, **kwargs)
    
    def error(self, msg: str, **kwargs):
        self._log_with_extra(logging.ERROR, msg, **kwargs)
    
    def critical(self, msg: str, **kwargs):
        self._log_with_extra(logging.CRITICAL, msg, **kwargs)
    
    def exception(self, msg: str, **kwargs):
        extra = {}
        if kwargs:
            extra['extra_data'] = kwargs
        self._logger.exception(msg, extra=extra)
    
    def log_operation(self, operation: str, level: int = logging.INFO, **kwargs):
        """Log an operation with structured context."""
        extra = {'operation': operation}
        if kwargs:
            extra['extra_data'] = kwargs
        self._logger.log(level, f"Operation: {operation}", extra=extra)
    
    def log_performance(self, operation: str, duration_ms: float, **kwargs):
        """Log performance metrics for an operation."""
        extra = {
            'operation': operation,
            'duration': duration_ms
        }
        if kwargs:
            extra['extra_data'] = kwargs
        self._logger.info(f"Performance: {operation} completed in {duration_ms:.2f}ms", extra=extra)
    
    def log_error_with_severity(self, msg: str, severity: str, **kwargs):
        """Log an error with severity level."""
        extra = {'severity': severity}
        if kwargs:
            extra['extra_data'] = kwargs
        self._logger.error(msg, extra=extra)


def get_logger(name):
    _logger = logging.getLogger(name)

    # set DEBUG level for the logger if the environment variable is set
    if os.getenv('DEBUG_LOG'):
        _logger.setLevel(logging.DEBUG)

    return _logger


def get_structured_logger(name):
    """Get a structured logger instance."""
    base_logger = get_logger(name)
    return StructuredLogger(base_logger)


logger = get_logger(__name__)

def init_sentry():
    """Deprecated. A candidate for removal in future versions."""

    sentry_dsn = os.getenv("SENTRY_DSN")
    if sentry_dsn:
        logger.info("Sentry enabled")
        sentry_sdk.init(
            dsn=sentry_dsn,
            # Add data like request headers and IP for users,
            # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
            send_default_pii=True,
            # Set traces_sample_rate to 1.0 to capture 100%
            # of transactions for tracing.
            traces_sample_rate=1.0,
            # Set profiles_sample_rate to 1.0 to profile 100%
            # of sampled transactions.
            # We recommend adjusting this value in production.
            profiles_sample_rate=1.0,
            environment=os.getenv("SENTRY_ENVIRONMENT", "dev"),
        )
    else:
        logger.warning("Sentry disabled")


def configure_uvicorn_logging():
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": _TEXT_FORMATTER._fmt,
            },
        },
        "loggers": {
            "uvicorn": {"level": "INFO", "propagate": True},
            "uvicorn.error": {"level": "INFO", "propagate": True},
            "uvicorn.access": {"level": "INFO", "propagate": True},
        },
    }

    return logging_config
