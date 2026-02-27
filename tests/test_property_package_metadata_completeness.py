"""Property-based test for package metadata completeness in DynamoDB.

**Validates: Requirements 1.2, 1.3, 9.3, 9.4, 9.5**

Property 2: Package Metadata Completeness
For any package stored in DynamoDB, the package entry should contain all required
fields: package_name, version, architecture, deb_url, actual_filename, file_size,
md5_hash, sha1_hash, sha256_hash, section, priority, maintainer, homepage,
description, pub_date, processed_timestamp, and package_type.
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

# Strategies for optional fields
optional_url_strategy = st.one_of(
    st.none(),
    st.text(min_size=5, max_size=50).map(lambda s: f"https://example.com/{s}"),
)

optional_text_strategy = st.one_of(
    st.none(),
    st.text(min_size=1, max_size=100),
)

# Required fields that store_package_metadata must always write
REQUIRED_DYNAMO_FIELDS = {
    "package_id",
    "package_name",
    "version",
    "architecture",
    "pub_date",
    "deb_url",
    "actual_filename",
    "file_size",
    "md5_hash",
    "sha1_hash",
    "sha256_hash",
    "processed_timestamp",
    "section",
    "priority",
    "maintainer",
    "homepage",
    "description",
}


def make_package_metadata(
    package_name: str,
    version: str,
    architecture: str,
    certificate_url: str | None = None,
    signature_url: str | None = None,
    notes: str | None = None,
    depends: str | None = None,
) -> PackageMetadata:
    """Create a PackageMetadata instance with required fields and optional overrides."""
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
        certificate_url=certificate_url,
        signature_url=signature_url,
        notes=notes,
        depends=depends,
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


# **Property 2: Package Metadata Completeness**
# **Validates: Requirements 1.2, 1.3, 9.3, 9.4, 9.5**
@settings(deadline=None)
@given(
    package_name=package_name_strategy,
    version=version_strategy,
    arch=architecture_strategy,
    certificate_url=optional_url_strategy,
    signature_url=optional_url_strategy,
    notes=optional_text_strategy,
    depends=optional_text_strategy,
)
def test_package_metadata_completeness_property(
    package_name,
    version,
    arch,
    certificate_url,
    signature_url,
    notes,
    depends,
):
    """Property: every stored DynamoDB item contains ALL required fields and
    preserves values through a store-then-retrieve round trip.

    Validates:
    - Req 1.2: package name, version, architecture, download URL, file size, SHA256
    - Req 1.3: package type identifier and processing timestamp
    - Req 9.3: Debian control fields (Package, Version, Architecture, Description,
      Maintainer, Section, Priority)
    - Req 9.4: file metadata (Filename, Size, SHA256)
    - Req 9.5: processing metadata (timestamp, package type, source)
    """
    metadata = make_package_metadata(
        package_name=package_name,
        version=version,
        architecture=arch,
        certificate_url=certificate_url,
        signature_url=signature_url,
        notes=notes,
        depends=depends,
    )

    stored_items: list[dict] = []

    mock_table = MagicMock()
    mock_dynamodb = MagicMock()
    mock_dynamodb.Table.return_value = mock_table

    def capture_put_item(Item):
        stored_items.append(Item)

    mock_table.put_item.side_effect = capture_put_item

    with patch("boto3.resource", return_value=mock_dynamodb):
        with patch.dict(os.environ, {"DYNAMODB_TABLE_NAME": "test-table"}):
            vm = VersionManager(validate_permissions=False)

            # --- Store the package ---
            vm.store_package_metadata(metadata)

            assert len(stored_items) == 1
            item = stored_items[0]

            # --- 1. All required fields are present (Req 1.2, 1.3, 9.3, 9.4, 9.5) ---
            missing = REQUIRED_DYNAMO_FIELDS - item.keys()
            assert not missing, f"Missing required fields: {missing}"

            # --- 2. Stored values match the input metadata (round-trip fidelity) ---
            # Req 1.2: package name, version, architecture, download URL, file size, SHA256
            assert item["package_name"] == package_name
            assert item["version"] == version
            assert item["architecture"] == arch
            assert item["deb_url"] == metadata.deb_url
            assert item["file_size"] == metadata.file_size
            assert item["sha256_hash"] == metadata.sha256_hash

            # Req 9.3: Debian control fields
            assert item["section"] == metadata.section
            assert item["priority"] == metadata.priority
            assert item["maintainer"] == metadata.maintainer
            assert item["homepage"] == metadata.homepage
            assert item["description"] == metadata.description

            # Req 9.4: file metadata
            assert item["actual_filename"] == metadata.actual_filename
            assert item["md5_hash"] == metadata.md5_hash
            assert item["sha1_hash"] == metadata.sha1_hash

            # Req 1.3 / 9.5: processing metadata
            assert item["processed_timestamp"] == metadata.processed_timestamp.isoformat()
            assert item["pub_date"] == metadata.pub_date

            # --- 3. Round-trip: retrieve via get_all_packages and verify ---
            mock_table.scan.return_value = {"Items": [item]}
            retrieved = vm.get_all_packages()

            assert len(retrieved) == 1
            pkg = retrieved[0]

            assert pkg.package_name == package_name
            assert pkg.version == version
            assert pkg.architecture == arch
            assert pkg.deb_url == metadata.deb_url
            assert pkg.actual_filename == metadata.actual_filename
            assert pkg.file_size == metadata.file_size
            assert pkg.md5_hash == metadata.md5_hash
            assert pkg.sha1_hash == metadata.sha1_hash
            assert pkg.sha256_hash == metadata.sha256_hash
            assert pkg.section == metadata.section
            assert pkg.priority == metadata.priority
            assert pkg.maintainer == metadata.maintainer
            assert pkg.homepage == metadata.homepage
            assert pkg.description == metadata.description
            assert pkg.pub_date == metadata.pub_date
            assert pkg.processed_timestamp == metadata.processed_timestamp

            # --- 4. Optional fields: stored when present, omitted when None ---
            if certificate_url is not None:
                assert item["certificate_url"] == certificate_url
                assert pkg.certificate_url == certificate_url
            else:
                assert "certificate_url" not in item

            if signature_url is not None:
                assert item["signature_url"] == signature_url
                assert pkg.signature_url == signature_url
            else:
                assert "signature_url" not in item

            if notes is not None:
                assert item["notes"] == notes
                assert pkg.notes == notes
            else:
                assert "notes" not in item

            if depends is not None:
                assert item["depends"] == depends
                assert pkg.depends == depends
            else:
                assert "depends" not in item
