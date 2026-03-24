"""Property-based tests for convenience copy functionality.

This module contains property tests for the kiro-repo.deb convenience copy
feature that validates the copy points to the latest version, is located at
the repository root, and is a regular S3 object.
"""

import time
from datetime import datetime
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError
from hypothesis import given, settings
from hypothesis import strategies as st

from src.models import PackageMetadata
from src.s3_publisher import S3Publisher

# --- Strategies ---

version_strategy = st.builds(
    lambda major, minor, patch_v: f"{major}.{minor}.{patch_v}",
    major=st.integers(min_value=0, max_value=99),
    minor=st.integers(min_value=0, max_value=99),
    patch_v=st.integers(min_value=0, max_value=999),
)

bucket_name_strategy = st.from_regex(r"^[a-z0-9][a-z0-9\-]{1,61}[a-z0-9]$")


def make_kiro_repo_metadata(version: str) -> PackageMetadata:
    """Create a PackageMetadata instance for kiro-repo package."""
    return PackageMetadata(
        package_name="kiro-repo",
        version=version,
        architecture="all",
        pub_date="2024-01-15",
        deb_url=f"https://example.com/kiro-repo_{version}.deb",
        actual_filename=f"kiro-repo_{version}_all.deb",
        file_size=2048,
        md5_hash="d41d8cd98f00b204e9800998ecf8427e",
        sha1_hash="da39a3ee5e6b4b0d3255bfef95601890afd80709",
        sha256_hash=(
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        ),
        processed_timestamp=datetime(2024, 1, 15, 12, 0, 0),
        section="admin",
        priority="optional",
        maintainer="Kiro Team <support@kiro.dev>",
        homepage="https://kiro.dev",
        description="Kiro APT repository configuration package",
    )


# --- Property Tests ---


# **Property 10: Convenience Copy Points to Latest Version**
# **Validates: Requirements 3.1, 3.3, 3.5**
@settings(deadline=None)
@given(
    bucket_name=bucket_name_strategy,
    version=version_strategy,
)
def test_convenience_copy_points_to_latest_version(bucket_name, version):
    """Property: The convenience copy kiro-repo.deb at repository root always
    points to the latest version of the kiro-repo package in the pool directory.

    Validates:
    - Req 3.1: Convenience copy exists at repository root
    - Req 3.3: Copy operation uses correct source path from pool
    - Req 3.5: Metadata includes version information
    """
    metadata = make_kiro_repo_metadata(version)

    # Track copy operations
    copy_operations = []

    def mock_copy_object(**kwargs):
        copy_operations.append(kwargs)
        return {}

    mock_s3_client = MagicMock()
    mock_s3_client.copy_object = MagicMock(side_effect=mock_copy_object)

    with patch("boto3.client", return_value=mock_s3_client):
        publisher = S3Publisher(
            bucket_name=bucket_name, region="us-east-1", validate_permissions=False
        )
        publisher.upload_convenience_copy(metadata)

    # Verify copy operation occurred
    assert len(copy_operations) == 1, "Should perform exactly one copy operation"

    copy_op = copy_operations[0]

    # Verify source path points to pool directory with correct structure
    expected_pool_key = f"pool/main/k/kiro-repo/kiro-repo_{version}_all.deb"
    assert copy_op["CopySource"]["Bucket"] == bucket_name
    assert copy_op["CopySource"]["Key"] == expected_pool_key, (
        f"Source should be {expected_pool_key}"
    )

    # Verify destination is repository root
    assert copy_op["Key"] == "kiro-repo.deb", (
        "Destination should be kiro-repo.deb at root"
    )

    # Verify metadata includes version
    assert "Metadata" in copy_op
    assert copy_op["Metadata"]["version"] == version, (
        "Metadata should include version"
    )
    assert copy_op["Metadata"]["package"] == "kiro-repo", (
        "Metadata should include package name"
    )


# **Property 11: Convenience Copy Location**
# **Validates: Requirements 3.2, 11.4**
@settings(deadline=None)
@given(
    bucket_name=bucket_name_strategy,
    version=version_strategy,
)
def test_convenience_copy_location(bucket_name, version):
    """Property: The convenience copy is always located at the repository root
    with the filename kiro-repo.deb, regardless of the actual package filename.

    Validates:
    - Req 3.2: Convenience copy location is repository root
    - Req 11.4: S3 key for convenience copy is kiro-repo.deb
    """
    metadata = make_kiro_repo_metadata(version)

    copy_operations = []

    def mock_copy_object(**kwargs):
        copy_operations.append(kwargs)
        return {}

    mock_s3_client = MagicMock()
    mock_s3_client.copy_object = MagicMock(side_effect=mock_copy_object)

    with patch("boto3.client", return_value=mock_s3_client):
        publisher = S3Publisher(
            bucket_name=bucket_name, region="us-east-1", validate_permissions=False
        )
        publisher.upload_convenience_copy(metadata)

    assert len(copy_operations) == 1

    copy_op = copy_operations[0]

    # Verify destination key is exactly "kiro-repo.deb" (no path prefix)
    assert copy_op["Key"] == "kiro-repo.deb", (
        "Convenience copy must be at repository root with name kiro-repo.deb"
    )

    # Verify bucket is correct
    assert copy_op["Bucket"] == bucket_name


# **Property 12: Convenience Copy is Regular Object**
# **Validates: Requirements 3.4**
@settings(deadline=None)
@given(
    bucket_name=bucket_name_strategy,
    version=version_strategy,
)
def test_convenience_copy_is_regular_object(bucket_name, version):
    """Property: The convenience copy is a regular S3 object (not a symlink or
    redirect), created using copy_object with appropriate Content-Type and ACL.

    Validates:
    - Req 3.4: Convenience copy is a regular S3 object with proper metadata
    """
    metadata = make_kiro_repo_metadata(version)

    copy_operations = []

    def mock_copy_object(**kwargs):
        copy_operations.append(kwargs)
        return {}

    mock_s3_client = MagicMock()
    mock_s3_client.copy_object = MagicMock(side_effect=mock_copy_object)

    with patch("boto3.client", return_value=mock_s3_client):
        publisher = S3Publisher(
            bucket_name=bucket_name, region="us-east-1", validate_permissions=False
        )
        publisher.upload_convenience_copy(metadata)

    assert len(copy_operations) == 1

    copy_op = copy_operations[0]

    # Verify it's a regular copy operation (not redirect)
    assert "CopySource" in copy_op, "Should use copy_object operation"

    # Verify Content-Type is set for Debian packages
    assert copy_op["ContentType"] == "application/vnd.debian.binary-package", (
        "Content-Type should be set for Debian packages"
    )

    # Verify no ACL is set (public access managed by bucket policy)
    assert "ACL" not in copy_op, "ACL should not be set (managed by bucket policy)"

    # Verify metadata directive is REPLACE (creates new object metadata)
    assert copy_op["MetadataDirective"] == "REPLACE", (
        "Should replace metadata to create independent object"
    )


# **Property 10: Convenience Copy Points to Latest Version (Retry Logic)**
# **Validates: Requirements 3.1, 3.3, 3.5**
@settings(deadline=None)
@given(
    bucket_name=bucket_name_strategy,
    version=version_strategy,
    failures_before_success=st.integers(min_value=1, max_value=2),
)
def test_convenience_copy_retry_logic(bucket_name, version, failures_before_success):
    """Property: The convenience copy upload retries on failure with exponential
    backoff, eventually succeeding if transient errors occur.

    Validates:
    - Req 3.1: Convenience copy is reliably created despite transient failures
    - Req 3.3: Retry logic ensures eventual consistency
    """
    metadata = make_kiro_repo_metadata(version)

    attempt_count = [0]

    def mock_copy_object(**kwargs):
        attempt_count[0] += 1
        if attempt_count[0] <= failures_before_success:
            # Simulate transient error
            error_response = {"Error": {"Code": "ServiceUnavailable"}}
            raise ClientError(error_response, "copy_object")
        return {}

    mock_s3_client = MagicMock()
    mock_s3_client.copy_object = MagicMock(side_effect=mock_copy_object)

    with patch("boto3.client", return_value=mock_s3_client):
        with patch("time.sleep"):  # Skip actual sleep in tests
            publisher = S3Publisher(
                bucket_name=bucket_name,
                region="us-east-1",
                validate_permissions=False,
            )
            publisher.upload_convenience_copy(metadata)

    # Verify retry occurred
    assert attempt_count[0] == failures_before_success + 1, (
        f"Should retry {failures_before_success} times before success"
    )


# **Property 10: Convenience Copy Points to Latest Version (Max Retries)**
# **Validates: Requirements 3.1**
@settings(deadline=None)
@given(
    bucket_name=bucket_name_strategy,
    version=version_strategy,
)
def test_convenience_copy_max_retries_exceeded(bucket_name, version):
    """Property: The convenience copy upload fails after max retries (3) if
    errors persist, raising the ClientError.

    Validates:
    - Req 3.1: Error handling for persistent failures
    """
    metadata = make_kiro_repo_metadata(version)

    attempt_count = [0]

    def mock_copy_object(**kwargs):
        attempt_count[0] += 1
        error_response = {"Error": {"Code": "ServiceUnavailable"}}
        raise ClientError(error_response, "copy_object")

    mock_s3_client = MagicMock()
    mock_s3_client.copy_object = MagicMock(side_effect=mock_copy_object)

    with patch("boto3.client", return_value=mock_s3_client):
        with patch("time.sleep"):  # Skip actual sleep in tests
            publisher = S3Publisher(
                bucket_name=bucket_name,
                region="us-east-1",
                validate_permissions=False,
            )

            try:
                publisher.upload_convenience_copy(metadata)
                assert False, "Should raise ClientError after max retries"
            except ClientError:
                pass  # Expected

    # Verify max retries (3) were attempted
    assert attempt_count[0] == 3, "Should attempt exactly 3 times before failing"
