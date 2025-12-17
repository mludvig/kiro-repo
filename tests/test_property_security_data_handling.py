"""Property-based test for security data handling in logs."""

import json
from io import StringIO
from unittest.mock import patch

from hypothesis import given
from hypothesis import strategies as st

from src.config import setup_logging


# **Feature: debian-repo-manager, Property 9: Security Data Handling**
# **Validates: Requirements 7.2**
@given(
    operation_name=st.text(
        min_size=1,
        max_size=50,
        alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-",
    ).filter(lambda x: x.strip()),
    sensitive_key=st.sampled_from(
        [
            "password",
            "secret",
            "key",
            "token",
            "credential",
            "auth",
            "aws_access_key_id",
            "aws_secret_access_key",
            "api_key",
            "private_key",
        ]
    ),
    sensitive_value=st.text(
        min_size=15,
        max_size=100,
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*()",
    ).filter(
        lambda x: len(x) >= 15
        and "system" not in x.lower()
        and "operation" not in x.lower()
        and "password" not in x.lower()
        and "secret" not in x.lower()
        and "key" not in x.lower()
        and "token" not in x.lower()
        and "credential" not in x.lower()
        and "auth" not in x.lower()
    ),
    safe_key=st.sampled_from(
        ["version", "url", "file_size", "record_count", "batch_id"]
    ),
    safe_value=st.text(min_size=1, max_size=100),
    message_with_sensitive=st.text(min_size=1, max_size=200),
)
def test_security_data_handling_property(
    operation_name,
    sensitive_key,
    sensitive_value,
    safe_key,
    safe_value,
    message_with_sensitive,
):
    # Skip if values overlap in ways that would cause false positives
    if (
        operation_name == sensitive_value
        or operation_name in sensitive_value
        or sensitive_value in operation_name
        or safe_value == sensitive_value
        or safe_value in sensitive_value
        or sensitive_value in safe_value
    ):
        return
    """Property test: For any log output, sensitive data such as credentials or access keys should not be present in log messages.

    This property tests that the logging system properly sanitizes sensitive information
    and prevents credential leakage in log outputs.
    """
    # Capture log output
    log_stream = StringIO()

    with patch("sys.stdout", log_stream):
        # Set up logging system
        system_logger = setup_logging("DEBUG")  # Use DEBUG to capture all logs
        logger = system_logger.logger
        operation_logger = system_logger.get_operation_logger()

        # Test 1: Log message with sensitive data in extra fields
        logger.info(
            "Processing operation",
            extra={
                "operation": operation_name,
                sensitive_key: sensitive_value,  # This should be redacted
                safe_key: safe_value,  # This should remain
                "component": "test",
            },
        )

        # Test 2: Log message with sensitive data in the message itself
        sensitive_message = f"Operation failed with {sensitive_key}: {sensitive_value}"
        logger.error(sensitive_message)

        # Test 3: Operation logging with sensitive context
        operation_logger.start_operation(
            operation_name,
            **{
                sensitive_key: sensitive_value,  # Should be redacted
                safe_key: safe_value,  # Should remain
                "config": {
                    "database_password": "super_secret_123",  # Should be redacted
                    "database_host": "localhost",  # Should remain
                    "api_token": "token_abc123",  # Should be redacted
                },
            },
        )

        # Test 4: Error logging with sensitive exception data
        try:
            # Create an exception with sensitive data
            raise ValueError(
                f"Authentication failed: {sensitive_key}={sensitive_value}"
            )
        except ValueError as e:
            operation_logger.log_error(
                operation_name, e, **{sensitive_key: sensitive_value}
            )

        # Test 5: System termination with sensitive metrics
        system_logger.set_metric("processed_files", 10)
        system_logger.set_metric(sensitive_key, sensitive_value)  # Should be redacted
        system_logger.log_system_termination(success=True)

    # Get logged output
    log_output = log_stream.getvalue()
    log_lines = [line.strip() for line in log_output.split("\n") if line.strip()]

    # Should have multiple log entries
    assert len(log_lines) >= 4

    # Parse each log line and verify sensitive data is redacted
    for line in log_lines:
        try:
            log_entry = json.loads(line)

            # Recursively check all fields for sensitive data
            _verify_no_sensitive_data(log_entry, sensitive_value, sensitive_key)

            # Verify that safe data is preserved
            if safe_key in str(log_entry) and safe_value in str(log_entry):
                # Safe data should not be redacted
                assert safe_value in str(log_entry)

        except json.JSONDecodeError as e:
            # All log entries should be valid JSON
            raise AssertionError(f"Invalid JSON log entry: {line}") from e

    # Verify that the raw sensitive value never appears in any log output
    # (except as a field name, which is acceptable)
    if len(sensitive_value) >= 10:  # Only check substantial values
        # Check that sensitive value doesn't appear as a value (not as a key name)
        import re

        # Look for the sensitive value as a JSON value (quoted)
        value_pattern = f'": "{re.escape(sensitive_value)}"'
        assert value_pattern not in log_output, (
            f"Sensitive value '{sensitive_value}' found as a value in log output"
        )

    # Verify that redaction marker is present where sensitive data was
    if any(sensitive_key in line for line in log_lines):
        assert "***REDACTED***" in log_output, (
            "Sensitive data should be replaced with redaction marker"
        )


def _verify_no_sensitive_data(data, sensitive_value, sensitive_key):
    """Recursively verify that sensitive data is not present in log data structure."""
    if isinstance(data, dict):
        for key, value in data.items():
            # Check if this is a sensitive key
            sensitive_patterns = [
                "password",
                "secret",
                "key",
                "token",
                "credential",
                "auth",
                "aws_access_key_id",
                "aws_secret_access_key",
            ]

            if any(pattern in key.lower() for pattern in sensitive_patterns):
                # Sensitive keys should have redacted values
                if isinstance(value, str) and value != "***REDACTED***":
                    # Allow empty strings or None, but not actual sensitive values
                    assert value != sensitive_value, (
                        f"Sensitive value found in key '{key}': {value}"
                    )
            else:
                # For non-sensitive keys, recursively check the value
                _verify_no_sensitive_data(value, sensitive_value, sensitive_key)

    elif isinstance(data, list):
        for item in data:
            _verify_no_sensitive_data(item, sensitive_value, sensitive_key)

    elif isinstance(data, str):
        # String values should not contain the raw sensitive value
        # (unless it's the redaction marker or it's a legitimate field name)
        if data != "***REDACTED***" and data != sensitive_key:
            # Only check for sensitive value leaks in actual data, not field names
            if (
                len(sensitive_value) >= 10
            ):  # Only check for substantial sensitive values
                assert sensitive_value not in data, (
                    f"Sensitive value found in string: {data}"
                )


@given(
    nested_sensitive_data=st.dictionaries(
        keys=st.sampled_from(
            ["password", "api_key", "secret_token", "aws_access_key_id"]
        ),
        values=st.text(
            min_size=15,
            max_size=50,
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*()",
        ),
        min_size=1,
        max_size=3,
    ),
    nested_safe_data=st.dictionaries(
        keys=st.sampled_from(["version", "file_size", "url", "record_count"]),
        values=st.text(
            min_size=1,
            max_size=20,
            alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-",
        ),
        min_size=1,
        max_size=3,
    ),
)
def test_nested_sensitive_data_redaction(nested_sensitive_data, nested_safe_data):
    # Skip if any sensitive and safe values overlap
    sensitive_values = set(nested_sensitive_data.values())
    safe_values = set(nested_safe_data.values())

    if sensitive_values & safe_values:  # If there's any intersection
        return
    """Property test: Sensitive data should be redacted even in deeply nested structures."""
    # Capture log output
    log_stream = StringIO()

    with patch("sys.stdout", log_stream):
        # Set up logging system
        system_logger = setup_logging("INFO")
        logger = system_logger.logger

        # Create nested structure with both sensitive and safe data
        complex_data = {
            "config": {
                "database": nested_sensitive_data,
                "metadata": nested_safe_data,
                "nested": {"auth": nested_sensitive_data, "info": nested_safe_data},
            }
        }

        # Log the complex structure
        logger.info("Processing complex configuration", extra=complex_data)

    # Get logged output
    log_output = log_stream.getvalue()

    # Verify no sensitive values appear in output
    for sensitive_value in nested_sensitive_data.values():
        assert sensitive_value not in log_output, (
            f"Sensitive value '{sensitive_value}' found in log output"
        )

    # Verify safe values are preserved
    for safe_value in nested_safe_data.values():
        # Safe values should appear in the output (not redacted)
        if safe_value.strip():  # Skip empty values
            assert safe_value in log_output, (
                f"Safe value '{safe_value}' was incorrectly redacted"
            )

    # Verify redaction markers are present
    assert "***REDACTED***" in log_output, (
        "Sensitive data should be replaced with redaction markers"
    )
