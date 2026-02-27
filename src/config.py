"""Configuration and logging setup for the Debian Repository Manager."""

import json
import logging
import os
import sys
import time
from datetime import UTC, datetime
from typing import Any


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured logging compatible with CloudWatch."""

    def __init__(self):
        super().__init__()

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON."""
        # Create base log entry
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add all extra fields from the record
        # Skip built-in logging fields
        builtin_fields = {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "getMessage",
            "exc_info",
            "exc_text",
            "stack_info",
            "taskName",
        }

        for key, value in record.__dict__.items():
            if key not in builtin_fields and key not in log_entry:
                log_entry[key] = value

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)


class OperationLogger:
    """Logger for tracking operations with metrics and timing."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.operation_start_times: dict[str, float] = {}
        self.operation_metrics: dict[str, dict[str, Any]] = {}

    def start_operation(self, operation: str, **kwargs) -> None:
        """Start tracking an operation."""
        self.operation_start_times[operation] = time.time()
        self.operation_metrics[operation] = kwargs

        self.logger.info(
            f"Starting operation: {operation}",
            extra={
                "operation": operation,
                "component": "operation_tracker",
                **kwargs,
            },
        )

    def complete_operation(
        self, operation: str, success: bool = True, **metrics
    ) -> None:
        """Complete an operation and log results with metrics."""
        start_time = self.operation_start_times.pop(operation, time.time())
        duration_ms = int((time.time() - start_time) * 1000)

        # Merge with initial metrics
        all_metrics = self.operation_metrics.pop(operation, {})
        all_metrics.update(metrics)

        status = "completed" if success else "failed"
        level = logging.INFO if success else logging.ERROR

        self.logger.log(
            level,
            f"Operation {status}: {operation}",
            extra={
                "operation": operation,
                "duration_ms": duration_ms,
                "metrics": all_metrics,
                "component": "operation_tracker",
                "success": success,
            },
        )

    def log_error(self, operation: str, error: Exception, **context) -> None:
        """Log an operation error with context."""
        # Calculate duration if operation was started
        duration_ms = 0
        if operation in self.operation_start_times:
            start_time = self.operation_start_times[operation]
            duration_ms = int((time.time() - start_time) * 1000)

        self.logger.error(
            f"Operation failed: {operation} - {str(error)}",
            extra={
                "operation": operation,
                "duration_ms": duration_ms,
                "error_code": type(error).__name__,
                "component": "operation_tracker",
                **context,
            },
            exc_info=True,
        )


class SystemLogger:
    """System-wide logger for comprehensive logging and metrics."""

    def __init__(self, name: str = "debian-repo-manager"):
        self.logger = logging.getLogger(name)
        self.operation_logger = OperationLogger(self.logger)
        self.system_start_time = time.time()
        self.system_metrics = {
            "operations_completed": 0,
            "operations_failed": 0,
            "files_processed": 0,
            "bytes_transferred": 0,
        }

    def log_system_start(self, **context) -> None:
        """Log system startup."""
        self.logger.info(
            "System starting up",
            extra={
                "operation": "system_startup",
                "component": "system",
                "metrics": context,
            },
        )

    def log_system_termination(self, success: bool = True) -> None:
        """Log system termination with summary metrics."""
        duration_ms = int((time.time() - self.system_start_time) * 1000)

        self.logger.info(
            f"System terminating - {'success' if success else 'failure'}",
            extra={
                "operation": "system_termination",
                "duration_ms": duration_ms,
                "metrics": self.system_metrics,
                "component": "system",
                "success": success,
            },
        )

    def increment_metric(self, metric: str, value: int = 1) -> None:
        """Increment a system metric."""
        if metric in self.system_metrics:
            self.system_metrics[metric] += value

    def set_metric(self, metric: str, value: Any) -> None:
        """Set a system metric value."""
        self.system_metrics[metric] = value

    def get_operation_logger(self) -> OperationLogger:
        """Get the operation logger instance."""
        return self.operation_logger


def setup_logging(level: str | None = None) -> SystemLogger:
    """Set up structured logging compatible with CloudWatch.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR). Defaults to INFO.

    Returns:
        SystemLogger instance for application use
    """
    log_level = level or os.getenv("LOG_LEVEL", "INFO")

    # Create structured formatter
    formatter = StructuredFormatter()

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add structured handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Set boto3 logging to WARNING to reduce noise
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    # Create and return system logger
    system_logger = SystemLogger()
    return system_logger


def get_env_var(name: str, default: str | None = None, required: bool = False) -> str:
    """Get environment variable with optional default and validation.

    Args:
        name: Environment variable name
        default: Default value if not set
        required: Whether the variable is required

    Returns:
        Environment variable value

    Raises:
        ValueError: If required variable is not set
    """
    value = os.getenv(name, default)

    if required and not value:
        raise ValueError(f"Required environment variable {name} is not set")

    return value or ""


# Environment variable names
ENV_S3_BUCKET = "S3_BUCKET_NAME"
ENV_DYNAMODB_TABLE = "DYNAMODB_TABLE_NAME"
ENV_LOG_LEVEL = "LOG_LEVEL"
ENV_AWS_REGION = "AWS_REGION"
