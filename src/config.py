"""Configuration and logging setup for the Debian Repository Manager."""

import logging
import os
import sys


def setup_logging(level: str | None = None) -> None:
    """Set up structured logging compatible with CloudWatch.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR). Defaults to INFO.
    """
    log_level = level or os.getenv("LOG_LEVEL", "INFO")

    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Set boto3 logging to WARNING to reduce noise
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


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
