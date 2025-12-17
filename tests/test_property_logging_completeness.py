"""Property-based test for logging completeness."""

import json
from io import StringIO
from unittest.mock import patch

from hypothesis import given
from hypothesis import strategies as st

from src.config import setup_logging


# **Feature: debian-repo-manager, Property 8: Logging Completeness**
# **Validates: Requirements 5.1, 5.3, 5.4, 5.5**
@given(
    operation_name=st.text(
        min_size=1,
        max_size=50,
        alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-",
    ).filter(lambda x: x.strip()),
    success=st.booleans(),
    duration_ms=st.integers(min_value=1, max_value=60000),
    files_count=st.integers(min_value=0, max_value=100),
    bytes_transferred=st.integers(min_value=0, max_value=1000000),
    error_message=st.text(max_size=100),
)
def test_logging_completeness_property(
    operation_name, success, duration_ms, files_count, bytes_transferred, error_message
):
    """Property test: For any system operation, appropriate log messages should be generated with structured format compatible with CloudWatch.

    This property tests that all system operations generate complete, structured log entries
    that include required fields and maintain CloudWatch compatibility.
    """
    # Capture log output
    log_stream = StringIO()

    with patch("sys.stdout", log_stream):
        # Set up logging system
        system_logger = setup_logging("INFO")
        operation_logger = system_logger.get_operation_logger()

        # Test operation logging
        operation_logger.start_operation(
            operation_name, files_count=files_count, expected_bytes=bytes_transferred
        )

        if success:
            operation_logger.complete_operation(
                operation_name,
                success=True,
                files_processed=files_count,
                bytes_transferred=bytes_transferred,
            )
        else:
            # Create a test exception
            test_error = ValueError(error_message)
            operation_logger.log_error(operation_name, test_error)
            operation_logger.complete_operation(
                operation_name,
                success=False,
                files_processed=files_count,
                bytes_transferred=bytes_transferred,
            )

        # Test system termination logging
        system_logger.log_system_termination(success=success)

    # Get logged output
    log_output = log_stream.getvalue()
    log_lines = [line.strip() for line in log_output.split("\n") if line.strip()]

    # Should have at least 2 log entries (start + complete/error, termination)
    assert len(log_lines) >= 2

    # Parse each log line as JSON to verify structure
    parsed_logs = []
    for line in log_lines:
        try:
            log_entry = json.loads(line)
            parsed_logs.append(log_entry)
        except json.JSONDecodeError as e:
            # All log entries should be valid JSON
            raise AssertionError(f"Invalid JSON log entry: {line}") from e

    # Verify required fields are present in all log entries
    required_fields = ["timestamp", "level", "logger", "message"]
    for log_entry in parsed_logs:
        for field in required_fields:
            assert field in log_entry, (
                f"Missing required field '{field}' in log entry: {log_entry}"
            )

        # Verify timestamp format (ISO 8601)
        timestamp = log_entry["timestamp"]
        assert (
            "T" in timestamp
            and "Z" in timestamp
            or "+" in timestamp
            or "-" in timestamp[-6:]
        )

        # Verify log level is valid
        assert log_entry["level"] in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

    # Find operation start log
    start_logs = [log for log in parsed_logs if "Starting operation" in log["message"]]
    assert len(start_logs) >= 1, "Should have operation start log"

    start_log = start_logs[0]
    assert "operation" in start_log
    assert start_log["operation"] == operation_name
    assert "component" in start_log
    assert start_log["component"] == "operation_tracker"

    # Find operation completion logs (not error logs)
    if success:
        completion_logs = [
            log for log in parsed_logs if "Operation completed" in log["message"]
        ]
    else:
        completion_logs = [
            log
            for log in parsed_logs
            if "Operation failed" in log["message"] and "metrics" in log
        ]

    assert len(completion_logs) >= 1, (
        f"Should have operation completion log. Found logs: {[log['message'] for log in parsed_logs]}"
    )

    completion_log = completion_logs[0]
    assert "operation" in completion_log
    assert completion_log["operation"] == operation_name
    assert "duration_ms" in completion_log
    assert isinstance(completion_log["duration_ms"], int)
    assert completion_log["duration_ms"] >= 0
    assert "metrics" in completion_log
    assert "success" in completion_log
    assert completion_log["success"] == success

    # Verify metrics are present and contain expected data
    metrics = completion_log["metrics"]
    assert isinstance(metrics, dict)
    if success:
        assert "files_processed" in metrics
        assert "bytes_transferred" in metrics
        assert metrics["files_processed"] == files_count
        assert metrics["bytes_transferred"] == bytes_transferred

    # Find system termination log
    termination_logs = [
        log for log in parsed_logs if "System terminating" in log["message"]
    ]
    assert len(termination_logs) >= 1, "Should have system termination log"

    termination_log = termination_logs[0]
    assert "operation" in termination_log
    assert termination_log["operation"] == "system_termination"
    assert "duration_ms" in termination_log
    assert "metrics" in termination_log
    assert "success" in termination_log
    assert termination_log["success"] == success

    # Verify system metrics are present
    system_metrics = termination_log["metrics"]
    assert isinstance(system_metrics, dict)
    expected_system_metrics = [
        "operations_completed",
        "operations_failed",
        "files_processed",
        "bytes_transferred",
    ]
    for metric in expected_system_metrics:
        assert metric in system_metrics
        assert isinstance(system_metrics[metric], int)

    # If operation failed, verify error logging
    if not success:
        error_logs = [
            log
            for log in parsed_logs
            if log["level"] == "ERROR" and "Operation failed" in log["message"]
        ]
        assert len(error_logs) >= 1, "Should have error log for failed operation"

        error_log = error_logs[0]
        assert "operation" in error_log
        assert error_log["operation"] == operation_name
        assert "error_code" in error_log
        assert error_log["error_code"] == "ValueError"
        assert "exception" in error_log  # Should include stack trace
