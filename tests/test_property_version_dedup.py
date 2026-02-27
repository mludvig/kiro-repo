"""Property-based test for version deduplication.

**Property 18: Version Deduplication**
**Validates: Requirements 18.2**

For any package with package_name P and version V, if a package entry with
package_id "P#V" already exists in DynamoDB, is_package_version_processed
should return True and the system should skip processing that version.
"""

import os
from datetime import datetime
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from src.models import PackageMetadata
from src.version_manager import VersionManager

# --- Strategies ---

KNOWN_PACKAGE_TYPES = ["kiro", "kiro-repo", "kiro-cli"]

version_strategy = st.builds(
    lambda major, minor, patch_v: f"{major}.{minor}.{patch_v}",
    major=st.integers(min_value=0, max_value=99),
    minor=st.integers(min_value=0, max_value=99),
    patch_v=st.integers(min_value=0, max_value=999),
)

package_name_strategy = st.sampled_from(KNOWN_PACKAGE_TYPES)

architecture_strategy = st.sampled_from(["amd64", "all", "arm64"])


def make_package_metadata(
    package_name: str,
    version: str,
    architecture: str,
) -> PackageMetadata:
    """Create a PackageMetadata instance with required fields."""
    return PackageMetadata(
        package_name=package_name,
        version=version,
        architecture=architecture,
        pub_date="2024-01-15",
        deb_url=f"https://example.com/{package_name}_{version}.deb",
        actual_filename=f"{package_name}_{version}_{architecture}.deb",
        file_size=1024,
        md5_hash="d41d8cd98f00b204e9800998ecf8427e",
        sha1_hash="da39a3ee5e6b4b0d3255bfef95601890afd80709",
        sha256_hash=(
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        ),
        processed_timestamp=datetime(2024, 1, 15, 12, 0, 0),
        section="editors",
        priority="optional",
        maintainer="Kiro Team <support@kiro.dev>",
        homepage="https://kiro.dev",
        description=f"{package_name} package",
    )


def _build_dynamo_item(metadata: PackageMetadata) -> dict:
    """Build the DynamoDB item dict that store_package_metadata would write."""
    item = {
        "package_id": metadata.package_id,
        "package_name": metadata.package_name,
        "version": metadata.version,
        "architecture": metadata.architecture,
        "pub_date": metadata.pub_date,
        "deb_url": metadata.deb_url,
        "actual_filename": metadata.actual_filename,
        "file_size": metadata.file_size,
        "md5_hash": metadata.md5_hash,
        "sha1_hash": metadata.sha1_hash,
        "sha256_hash": metadata.sha256_hash,
        "processed_timestamp": metadata.processed_timestamp.isoformat(),
        "section": metadata.section,
        "priority": metadata.priority,
        "maintainer": metadata.maintainer,
        "homepage": metadata.homepage,
        "description": metadata.description,
    }
    if metadata.certificate_url is not None:
        item["certificate_url"] = metadata.certificate_url
    if metadata.signature_url is not None:
        item["signature_url"] = metadata.signature_url
    if metadata.notes is not None:
        item["notes"] = metadata.notes
    if metadata.depends is not None:
        item["depends"] = metadata.depends
    return item


# --- Property Tests ---


# **Property 18: Version Deduplication**
# **Validates: Requirements 18.2**
@settings(deadline=None)
@given(
    pkg_name=package_name_strategy,
    version=version_strategy,
    arch=architecture_strategy,
)
def test_existing_version_detected_as_processed(pkg_name, version, arch):
    """Property: when a package_id exists in DynamoDB, is_package_version_processed
    returns True, indicating the version should be skipped.

    Validates:
    - Req 18.2: When a package version already exists in DynamoDB_Store,
      the system shall skip downloading and processing
    """
    make_package_metadata(pkg_name, version, arch)
    expected_id = f"{pkg_name}#{version}"

    mock_table = MagicMock()
    mock_dynamodb = MagicMock()
    mock_dynamodb.Table.return_value = mock_table

    # Simulate item exists in DynamoDB
    mock_table.get_item.return_value = {"Item": {"package_id": expected_id}}

    with patch("boto3.resource", return_value=mock_dynamodb):
        with patch.dict(os.environ, {"DYNAMODB_TABLE_NAME": "test-table"}):
            vm = VersionManager(validate_permissions=False)
            result = vm.is_package_version_processed(pkg_name, version)

    assert result is True, (
        f"Expected True for existing package {expected_id}, got {result}"
    )

    # Verify the correct package_id was queried
    mock_table.get_item.assert_called_once()
    call_key = mock_table.get_item.call_args[1]["Key"]
    assert call_key["package_id"] == expected_id, (
        f"Expected query for '{expected_id}', got '{call_key['package_id']}'"
    )


# **Property 18: Version Deduplication**
# **Validates: Requirements 18.2**
@settings(deadline=None)
@given(
    pkg_name=package_name_strategy,
    version=version_strategy,
)
def test_missing_version_detected_as_unprocessed(pkg_name, version):
    """Property: when a package_id does NOT exist in DynamoDB,
    is_package_version_processed returns False.

    Validates:
    - Req 18.2: Only existing versions are skipped; new versions proceed
    """
    expected_id = f"{pkg_name}#{version}"

    mock_table = MagicMock()
    mock_dynamodb = MagicMock()
    mock_dynamodb.Table.return_value = mock_table

    # Simulate item does NOT exist
    mock_table.get_item.return_value = {}

    with patch("boto3.resource", return_value=mock_dynamodb):
        with patch.dict(os.environ, {"DYNAMODB_TABLE_NAME": "test-table"}):
            vm = VersionManager(validate_permissions=False)
            result = vm.is_package_version_processed(pkg_name, version)

    assert result is False, (
        f"Expected False for missing package {expected_id}, got {result}"
    )


# **Property 18: Version Deduplication**
# **Validates: Requirements 18.2**
@settings(deadline=None)
@given(
    pkg_name=package_name_strategy,
    version=version_strategy,
    arch=architecture_strategy,
)
def test_store_then_check_is_consistent(pkg_name, version, arch):
    """Property: after storing a package via store_package_metadata, checking
    is_package_version_processed for the same name+version returns True.

    Validates:
    - Req 18.2: Stored versions are correctly detected as processed
    """
    pkg = make_package_metadata(pkg_name, version, arch)
    expected_id = f"{pkg_name}#{version}"

    mock_table = MagicMock()
    mock_dynamodb = MagicMock()
    mock_dynamodb.Table.return_value = mock_table

    # put_item succeeds silently
    mock_table.put_item.return_value = {}

    # After storing, get_item returns the item
    mock_table.get_item.return_value = {"Item": {"package_id": expected_id}}

    with patch("boto3.resource", return_value=mock_dynamodb):
        with patch.dict(os.environ, {"DYNAMODB_TABLE_NAME": "test-table"}):
            vm = VersionManager(validate_permissions=False)

            # Store the package
            vm.store_package_metadata(pkg)

            # Verify put_item was called with correct package_id
            put_call = mock_table.put_item.call_args[1]["Item"]
            assert put_call["package_id"] == expected_id

            # Now check deduplication
            result = vm.is_package_version_processed(pkg_name, version)

    assert result is True, f"Expected True after storing {expected_id}, got {result}"


# **Property 18: Version Deduplication**
# **Validates: Requirements 18.2**
@settings(deadline=None)
@given(
    pkg_names=st.lists(
        package_name_strategy,
        min_size=2,
        max_size=3,
        unique=True,
    ),
    version=version_strategy,
)
def test_dedup_is_scoped_to_package_name(pkg_names, version):
    """Property: deduplication is scoped by package_name — storing kiro#1.0
    does not cause is_package_version_processed to return True for
    kiro-repo#1.0.

    Validates:
    - Req 18.2: Deduplication uses composite key (package_name + version)
    """
    stored_name = pkg_names[0]
    other_name = pkg_names[1]

    stored_id = f"{stored_name}#{version}"
    other_id = f"{other_name}#{version}"

    mock_table = MagicMock()
    mock_dynamodb = MagicMock()
    mock_dynamodb.Table.return_value = mock_table

    def get_item_side_effect(**kwargs):
        key = kwargs["Key"]["package_id"]
        if key == stored_id:
            return {"Item": {"package_id": stored_id}}
        return {}

    mock_table.get_item.side_effect = get_item_side_effect

    with patch("boto3.resource", return_value=mock_dynamodb):
        with patch.dict(os.environ, {"DYNAMODB_TABLE_NAME": "test-table"}):
            vm = VersionManager(validate_permissions=False)

            # Stored name should be detected
            assert vm.is_package_version_processed(stored_name, version) is True

            # Different name with same version should NOT be detected
            assert vm.is_package_version_processed(other_name, version) is False, (
                f"Dedup leaked: {stored_id} exists but {other_id} "
                f"was incorrectly reported as processed"
            )
