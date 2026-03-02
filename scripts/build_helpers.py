"""Helper utilities for the kiro-repo build script.

These functions encapsulate the Python-testable logic used by
build-kiro-repo.sh and can be invoked directly or tested in isolation.
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Terraform state parsing
# ---------------------------------------------------------------------------

REQUIRED_OUTPUTS = ("s3_bucket_name", "dynamodb_table_name", "lambda_function_name")


def load_terraform_state(state_file: Path) -> dict[str, Any]:
    """Load and parse a Terraform state file.

    Args:
        state_file: Path to the .tfstate JSON file.

    Returns:
        Parsed state as a dictionary.

    Raises:
        FileNotFoundError: If the state file does not exist.
        ValueError: If the file is not valid JSON.
    """
    if not state_file.exists():
        raise FileNotFoundError(
            f"Terraform state file not found: {state_file}. "
            "Ensure Terraform has been applied for this environment."
        )

    try:
        return json.loads(state_file.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in state file {state_file}: {exc}") from exc


def extract_terraform_outputs(state: dict[str, Any]) -> dict[str, str]:
    """Extract output values from a parsed Terraform state.

    Args:
        state: Parsed Terraform state dictionary.

    Returns:
        Dictionary mapping output name to its string value.

    Raises:
        KeyError: If the state has no 'outputs' section.
    """
    outputs_raw: dict[str, Any] = state.get("outputs", {})
    return {
        name: entry["value"]
        for name, entry in outputs_raw.items()
        if isinstance(entry, dict) and "value" in entry
    }


def validate_required_outputs(
    outputs: dict[str, str],
    required: tuple[str, ...] = REQUIRED_OUTPUTS,
) -> None:
    """Validate that all required Terraform outputs are present and non-empty.

    Args:
        outputs: Extracted output values.
        required: Names of required output keys.

    Raises:
        ValueError: If any required output is missing or empty.
    """
    missing = [key for key in required if not outputs.get(key)]
    if missing:
        raise ValueError(
            f"Missing required Terraform outputs: {', '.join(missing)}. "
            "Ensure the Terraform outputs are defined and the state is up to date."
        )


def get_infrastructure_config(
    state_file: Path,
) -> dict[str, str]:
    """Load Terraform state and return infrastructure resource names.

    Combines load, extract, and validate into a single call.

    Args:
        state_file: Path to the environment's .tfstate file.

    Returns:
        Dictionary with keys: s3_bucket_name, dynamodb_table_name,
        lambda_function_name, and optionally s3_bucket_website_endpoint.

    Raises:
        FileNotFoundError: If the state file does not exist.
        ValueError: If required outputs are missing or the file is invalid JSON.
    """
    state = load_terraform_state(state_file)
    outputs = extract_terraform_outputs(state)
    validate_required_outputs(outputs)
    return outputs


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------

def is_valid_version(version: str) -> bool:
    """Check whether a version string matches the expected X.Y or X.Y.Z format.

    Args:
        version: Version string to validate.

    Returns:
        True if the version matches X.Y or X.Y.Z, False otherwise.
    """
    parts = version.split(".")
    if len(parts) not in (2, 3):
        return False
    return all(part.isdigit() for part in parts)


def derive_repo_url(outputs: dict[str, str]) -> str:
    """Derive the public repository URL from Terraform outputs.

    Prefers the website endpoint if available, otherwise falls back to
    the S3 bucket domain name.

    Args:
        outputs: Terraform output values.

    Returns:
        Repository base URL string.
    """
    website = outputs.get("s3_bucket_website_endpoint", "")
    if website:
        return f"http://{website}"
    bucket = outputs["s3_bucket_name"]
    return f"https://{bucket}.s3.amazonaws.com"


# ---------------------------------------------------------------------------
# Checksum computation
# ---------------------------------------------------------------------------

def compute_checksums(file_path: Path) -> dict[str, str]:
    """Compute MD5, SHA1, and SHA256 checksums for a file.

    Args:
        file_path: Path to the file to checksum.

    Returns:
        Dictionary with keys 'md5', 'sha1', 'sha256' mapping to hex digests.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    md5 = hashlib.md5()
    sha1 = hashlib.sha1()
    sha256 = hashlib.sha256()

    with open(file_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            md5.update(chunk)
            sha1.update(chunk)
            sha256.update(chunk)

    return {
        "md5": md5.hexdigest(),
        "sha1": sha1.hexdigest(),
        "sha256": sha256.hexdigest(),
    }


# ---------------------------------------------------------------------------
# DynamoDB item construction
# ---------------------------------------------------------------------------

def build_dynamodb_item(
    version: str,
    actual_filename: str,
    file_size: int,
    checksums: dict[str, str],
    staging_url: str,
    pub_date: str | None = None,
) -> dict[str, Any]:
    """Construct the DynamoDB item for a kiro-repo package.

    Args:
        version: Package version string (e.g., "1.2").
        actual_filename: The .deb filename (e.g., "kiro-repo_1.2_all.deb").
        file_size: File size in bytes.
        checksums: Dict with 'md5', 'sha1', 'sha256' hex digests.
        staging_url: S3 URL of the staged .deb file.
        pub_date: ISO-format publication date; defaults to current UTC time.

    Returns:
        DynamoDB item dictionary ready for put_item.
    """
    if pub_date is None:
        pub_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "package_id": f"kiro-repo#{version}",
        "package_name": "kiro-repo",
        "version": version,
        "architecture": "all",
        "pub_date": pub_date,
        "deb_url": staging_url,
        "actual_filename": actual_filename,
        "file_size": file_size,
        "md5_hash": checksums["md5"],
        "sha1_hash": checksums["sha1"],
        "sha256_hash": checksums["sha256"],
        "section": "misc",
        "priority": "optional",
        "maintainer": "Kiro Team <support@kiro.dev>",
        "homepage": "https://kiro.dev",
        "description": "Kiro IDE Repository Configuration",
        "package_type": "build_script",
        "processed_timestamp": pub_date,
    }
