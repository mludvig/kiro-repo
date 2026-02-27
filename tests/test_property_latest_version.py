"""Property-based test for latest version identification.

**Property 6: Latest Version Identification**
**Validates: Requirements 1.7**

For any set of packages with the same package_name stored in DynamoDB,
get_latest_package should return the package whose version is the maximum
according to semantic version comparison (parse_version).
"""

import os
from datetime import datetime
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from src.models import PackageMetadata
from src.utils import parse_version
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


# **Property 6: Latest Version Identification**
# **Validates: Requirements 1.7**
@settings(deadline=None)
@given(
    pkg_name=package_name_strategy,
    versions=st.lists(
        version_strategy,
        min_size=1,
        max_size=10,
        unique=True,
    ),
    arch=architecture_strategy,
)
def test_get_latest_package_returns_max_version(pkg_name, versions, arch):
    """Property: get_latest_package always returns the package whose version
    is the semantic maximum among all stored versions for that package name.

    Validates:
    - Req 1.7: DynamoDB_Store supports querying the latest version of each
      package type
    """
    packages = [make_package_metadata(pkg_name, v, arch) for v in versions]
    items = [_build_dynamo_item(p) for p in packages]

    # Determine expected latest using the same parse_version logic
    expected_latest_version = max(versions, key=parse_version)

    mock_table = MagicMock()
    mock_dynamodb = MagicMock()
    mock_dynamodb.Table.return_value = mock_table

    # Mock scan to return all items for this package name
    mock_table.scan.return_value = {"Items": items}

    with patch("boto3.resource", return_value=mock_dynamodb):
        with patch.dict(os.environ, {"DYNAMODB_TABLE_NAME": "test-table"}):
            vm = VersionManager(validate_permissions=False)
            result = vm.get_latest_package(pkg_name)

    assert result is not None, (
        f"Expected a package but got None for '{pkg_name}' with versions {versions}"
    )
    assert result.version == expected_latest_version, (
        f"Expected latest version '{expected_latest_version}' "
        f"but got '{result.version}' for '{pkg_name}'"
    )
    assert result.package_name == pkg_name


# **Property 6: Latest Version Identification**
# **Validates: Requirements 1.7**
@settings(deadline=None)
@given(pkg_name=package_name_strategy)
def test_get_latest_package_returns_none_for_empty(pkg_name):
    """Property: get_latest_package returns None when no packages exist
    for the given package name.

    Validates:
    - Req 1.7: DynamoDB_Store supports querying the latest version of each
      package type (edge case: no packages)
    """
    mock_table = MagicMock()
    mock_dynamodb = MagicMock()
    mock_dynamodb.Table.return_value = mock_table

    mock_table.scan.return_value = {"Items": []}

    with patch("boto3.resource", return_value=mock_dynamodb):
        with patch.dict(os.environ, {"DYNAMODB_TABLE_NAME": "test-table"}):
            vm = VersionManager(validate_permissions=False)
            result = vm.get_latest_package(pkg_name)

    assert result is None, f"Expected None for empty package set, got {result}"


# **Property 6: Latest Version Identification**
# **Validates: Requirements 1.7**
@settings(deadline=None)
@given(
    pkg_name=package_name_strategy,
    version=version_strategy,
    arch=architecture_strategy,
)
def test_get_latest_package_single_version(pkg_name, version, arch):
    """Property: when only one version exists, get_latest_package returns it.

    Validates:
    - Req 1.7: DynamoDB_Store supports querying the latest version of each
      package type (single version case)
    """
    pkg = make_package_metadata(pkg_name, version, arch)
    items = [_build_dynamo_item(pkg)]

    mock_table = MagicMock()
    mock_dynamodb = MagicMock()
    mock_dynamodb.Table.return_value = mock_table

    mock_table.scan.return_value = {"Items": items}

    with patch("boto3.resource", return_value=mock_dynamodb):
        with patch.dict(os.environ, {"DYNAMODB_TABLE_NAME": "test-table"}):
            vm = VersionManager(validate_permissions=False)
            result = vm.get_latest_package(pkg_name)

    assert result is not None
    assert result.version == version
    assert result.package_name == pkg_name


# **Property 6: Latest Version Identification**
# **Validates: Requirements 1.7**
@settings(deadline=None)
@given(
    pkg_names=st.lists(
        package_name_strategy,
        min_size=2,
        max_size=3,
        unique=True,
    ),
    versions_per_pkg=st.lists(
        st.lists(version_strategy, min_size=1, max_size=5, unique=True),
        min_size=2,
        max_size=3,
    ),
    arch=architecture_strategy,
)
def test_get_latest_package_independent_per_name(pkg_names, versions_per_pkg, arch):
    """Property: get_latest_package for one package name is independent of
    versions stored for other package names.

    Validates:
    - Req 1.7: DynamoDB_Store supports querying the latest version of each
      package type (isolation between package types)
    """
    # Pair each name with its version list (truncate to match lengths)
    pairs = list(zip(pkg_names, versions_per_pkg, strict=False))

    mock_table = MagicMock()
    mock_dynamodb = MagicMock()
    mock_dynamodb.Table.return_value = mock_table

    with patch("boto3.resource", return_value=mock_dynamodb):
        with patch.dict(os.environ, {"DYNAMODB_TABLE_NAME": "test-table"}):
            vm = VersionManager(validate_permissions=False)

            for name, versions in pairs:
                packages = [make_package_metadata(name, v, arch) for v in versions]
                items = [_build_dynamo_item(p) for p in packages]
                expected_latest = max(versions, key=parse_version)

                # Mock returns only this package name's items
                mock_table.scan.return_value = {"Items": items}

                result = vm.get_latest_package(name)

                assert result is not None
                assert result.version == expected_latest, (
                    f"For '{name}', expected latest '{expected_latest}' "
                    f"but got '{result.version}'"
                )
                assert result.package_name == name
