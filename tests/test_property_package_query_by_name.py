"""Property-based test for package query by name in DynamoDB.

**Validates: Requirements 1.6**

Property 5: Package Query by Name
For any package name and set of packages in DynamoDB, querying by package name
should return only packages with that exact package_name value.
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

arbitrary_package_name = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-"),
    min_size=2,
    max_size=20,
).filter(lambda s: s[0].isalpha())

package_name_strategy = st.one_of(
    st.sampled_from(KNOWN_PACKAGE_TYPES),
    arbitrary_package_name,
)

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
        sha256_hash="e3b0c44298fc1c149afbf4c8996fb924"
        "27ae41e4649b934ca495991b7852b855",
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


# --- Property Test ---


# **Property 5: Package Query by Name**
# **Validates: Requirements 1.6**
@settings(deadline=None)
@given(
    pkg_names=st.lists(
        package_name_strategy,
        min_size=2,
        max_size=5,
        unique=True,
    ),
    versions=st.lists(
        version_strategy,
        min_size=1,
        max_size=3,
        unique=True,
    ),
    arch=architecture_strategy,
)
def test_package_query_by_name_property(pkg_names, versions, arch):
    """Property: querying by package name returns only packages with that
    exact package_name value, with correct count and no leakage.

    Validates:
    - Req 1.6: DynamoDB_Store supports querying all versions of a specific
      package type
    """
    # Build all packages (cross-product of names × versions)
    all_packages = [
        make_package_metadata(name, ver, arch)
        for name in pkg_names
        for ver in versions
    ]
    all_items = [_build_dynamo_item(p) for p in all_packages]

    mock_table = MagicMock()
    mock_dynamodb = MagicMock()
    mock_dynamodb.Table.return_value = mock_table

    with patch("boto3.resource", return_value=mock_dynamodb):
        with patch.dict(os.environ, {"DYNAMODB_TABLE_NAME": "test-table"}):
            vm = VersionManager(validate_permissions=False)

            for query_name in pkg_names:
                # Mock scan to return only items matching the queried name,
                # simulating the DynamoDB FilterExpression behaviour
                matching_items = [
                    item for item in all_items
                    if item["package_name"] == query_name
                ]
                mock_table.scan.return_value = {"Items": matching_items}

                result = vm.get_packages_by_name(query_name)

                # Exactness: every returned package has the queried name
                assert all(
                    p.package_name == query_name for p in result
                ), f"Found package with wrong name when querying '{query_name}'"

                # Completeness: count matches expected
                expected_count = len(versions)
                assert len(result) == expected_count, (
                    f"Expected {expected_count} packages for '{query_name}', "
                    f"got {len(result)}"
                )

                # No leakage: returned package_ids are a subset of expected
                expected_ids = {
                    f"{query_name}#{v}" for v in versions
                }
                returned_ids = {p.package_id for p in result}
                assert returned_ids == expected_ids, (
                    f"Package ID mismatch for '{query_name}': "
                    f"expected {expected_ids}, got {returned_ids}"
                )

            # --- Query for a name that doesn't exist ---
            nonexistent_name = "nonexistent-pkg-xyz"
            mock_table.scan.return_value = {"Items": []}
            result = vm.get_packages_by_name(nonexistent_name)
            assert result == [], (
                f"Expected empty list for nonexistent name, got {len(result)} items"
            )


# **Property 5: Package Query by Name – substring isolation**
# **Validates: Requirements 1.6**
@settings(deadline=None)
@given(
    versions=st.lists(
        version_strategy,
        min_size=1,
        max_size=3,
        unique=True,
    ),
    arch=architecture_strategy,
)
def test_package_query_by_name_no_substring_match(versions, arch):
    """Property: querying for a package name that is a substring of another
    name does not return false matches (e.g., querying 'kiro' must not
    return 'kiro-repo' or 'kiro-cli' packages).

    Validates:
    - Req 1.6: DynamoDB_Store supports querying all versions of a specific
      package type (exact match only)
    """
    # Use known names where one is a prefix of others
    names_with_prefix = ["kiro", "kiro-repo", "kiro-cli"]

    all_packages = [
        make_package_metadata(name, ver, arch)
        for name in names_with_prefix
        for ver in versions
    ]
    all_items = [_build_dynamo_item(p) for p in all_packages]

    mock_table = MagicMock()
    mock_dynamodb = MagicMock()
    mock_dynamodb.Table.return_value = mock_table

    with patch("boto3.resource", return_value=mock_dynamodb):
        with patch.dict(os.environ, {"DYNAMODB_TABLE_NAME": "test-table"}):
            vm = VersionManager(validate_permissions=False)

            for query_name in names_with_prefix:
                # Simulate exact-match filter: only items where
                # package_name == query_name (not substring/prefix match)
                matching_items = [
                    item for item in all_items
                    if item["package_name"] == query_name
                ]
                mock_table.scan.return_value = {"Items": matching_items}

                result = vm.get_packages_by_name(query_name)

                # Exactness: no substring leakage
                for pkg in result:
                    assert pkg.package_name == query_name, (
                        f"Querying '{query_name}' returned package with "
                        f"name '{pkg.package_name}' (substring leak)"
                    )

                # Count matches expected versions for this name only
                assert len(result) == len(versions), (
                    f"Expected {len(versions)} packages for '{query_name}', "
                    f"got {len(result)}"
                )
