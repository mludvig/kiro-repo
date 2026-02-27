"""Property-based test for multi-package type storage in DynamoDB.

**Validates: Requirements 1.1, 4.1, 4.2, 17.3**

Property 1: Multi-Package Type Storage
For any set of packages with different package types (kiro, kiro-repo, kiro-cli),
when stored in DynamoDB, all packages should be retrievable and correctly
identified by their package type.
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

# Strategy for arbitrary package names (tests extensibility / Req 17.3)
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


# **Property 1: Multi-Package Type Storage**
# **Validates: Requirements 1.1, 4.1, 4.2, 17.3**
@settings(deadline=None)
@given(
    pkg_names=st.lists(
        package_name_strategy,
        min_size=1,
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
def test_multi_package_type_storage_property(pkg_names, versions, arch):
    """Property: packages of different types stored in DynamoDB are all
    retrievable and correctly identified by their package type.

    Validates:
    - Req 1.1: DynamoDB stores Package_Entry records for all package types
    - Req 4.1: System supports multiple package types
    - Req 4.2: System identifies package type from metadata
    - Req 17.3: Schema supports arbitrary package types without changes
    """
    # Build all packages (cross-product of names × versions)
    all_packages = [
        make_package_metadata(name, ver, arch)
        for name in pkg_names
        for ver in versions
    ]

    # Collect items that would be stored in DynamoDB
    stored_items: list[dict] = []

    mock_table = MagicMock()
    mock_dynamodb = MagicMock()
    mock_dynamodb.Table.return_value = mock_table

    # Capture put_item calls
    def capture_put_item(Item):
        stored_items.append(Item)

    mock_table.put_item.side_effect = capture_put_item

    with patch("boto3.resource", return_value=mock_dynamodb):
        with patch.dict(os.environ, {"DYNAMODB_TABLE_NAME": "test-table"}):
            vm = VersionManager(validate_permissions=False)

            # --- Store all packages ---
            for pkg in all_packages:
                vm.store_package_metadata(pkg)

            # Verify correct number of put_item calls
            assert mock_table.put_item.call_count == len(all_packages)

            # --- Verify package_id format ---
            # Req 1.1, 4.2: each stored item has correct composite key
            for pkg, item in zip(all_packages, stored_items):
                expected_id = f"{pkg.package_name}#{pkg.version}"
                assert item["package_id"] == expected_id
                assert item["package_name"] == pkg.package_name
                assert item["version"] == pkg.version

            # --- Verify get_all_packages returns everything ---
            # Req 1.1: DynamoDB stores records for all package types
            mock_table.scan.return_value = {
                "Items": [_build_dynamo_item(p) for p in all_packages],
            }

            retrieved = vm.get_all_packages()
            assert len(retrieved) == len(all_packages)

            retrieved_ids = {p.package_id for p in retrieved}
            expected_ids = {p.package_id for p in all_packages}
            assert retrieved_ids == expected_ids

            # --- Verify get_packages_by_name filters correctly ---
            # Req 4.1, 4.2: system identifies and filters by package type
            for name in pkg_names:
                name_items = [
                    _build_dynamo_item(p)
                    for p in all_packages
                    if p.package_name == name
                ]
                mock_table.scan.return_value = {"Items": name_items}

                by_name = vm.get_packages_by_name(name)
                assert len(by_name) == len(versions)
                assert all(p.package_name == name for p in by_name)

            # --- Verify is_package_version_processed per type ---
            # Req 4.2: system identifies package by type + version
            for pkg in all_packages:
                mock_table.get_item.return_value = {
                    "Item": {"package_id": pkg.package_id}
                }
                assert vm.is_package_version_processed(
                    pkg.package_name, pkg.version
                )

            # A non-existent combo should return False
            mock_table.get_item.return_value = {}
            assert not vm.is_package_version_processed(
                "nonexistent-pkg", "0.0.0"
            )

            # --- Verify arbitrary package types work (Req 17.3) ---
            # The schema doesn't restrict package_name values;
            # this is already exercised by the arbitrary_package_name
            # strategy above, but we explicitly verify the stored items
            # contain whatever names were generated.
            stored_names = {item["package_name"] for item in stored_items}
            assert stored_names == set(pkg_names)
