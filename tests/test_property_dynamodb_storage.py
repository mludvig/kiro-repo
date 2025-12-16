"""Property-based test for DynamoDB storage completeness."""

import os
from datetime import datetime
from unittest.mock import MagicMock, patch

from hypothesis import given
from hypothesis import strategies as st

from src.models import ReleaseInfo
from src.version_manager import VersionManager


# **Feature: debian-repo-manager, Property 7: DynamoDB Storage Completeness**
# **Validates: Requirements 6.1, 6.2, 6.3**
@given(
    major=st.integers(min_value=0, max_value=99),
    minor=st.integers(min_value=0, max_value=99),
    patch_version=st.integers(min_value=0, max_value=999),
    pub_date=st.dates().map(str),
    domain=st.sampled_from(["example.com", "test.org", "download.kiro.dev"]),
    protocol=st.sampled_from(["http", "https"]),
    notes=st.text(max_size=100),
    timestamp=st.datetimes(
        min_value=datetime(2020, 1, 1), max_value=datetime(2030, 12, 31)
    ),
)
def test_dynamodb_storage_completeness_property(
    major, minor, patch_version, pub_date, domain, protocol, notes, timestamp
):
    """Property test: For any new package version, storing in DynamoDB should include all required fields and be retrievable via scan operations.

    This property tests that version storage includes all required fields
    (version, URLs, timestamp, checksum) and can be retrieved consistently.
    """
    # Create realistic version and URLs
    version = f"{major}.{minor}.{patch_version}"
    base_url = f"{protocol}://{domain}"

    # Create release info with all required fields
    release_info = ReleaseInfo(
        version=version,
        pub_date=str(pub_date),
        deb_url=f"{base_url}/package.deb",
        certificate_url=f"{base_url}/cert.pem",
        signature_url=f"{base_url}/sig.bin",
        notes=notes,
        processed_timestamp=timestamp,
    )

    # Mock DynamoDB operations to simulate storage and retrieval
    mock_table = MagicMock()
    mock_dynamodb = MagicMock()
    mock_dynamodb.Table.return_value = mock_table

    # Mock successful put_item operation
    mock_table.put_item.return_value = {}

    # Mock get_item to return the stored item
    stored_item = {
        "version": release_info.version,
        "deb_url": release_info.deb_url,
        "certificate_url": release_info.certificate_url,
        "signature_url": release_info.signature_url,
        "pub_date": release_info.pub_date,
        "processed_timestamp": release_info.processed_timestamp.isoformat(),
        "notes": release_info.notes,
    }
    mock_table.get_item.return_value = {"Item": stored_item}

    # Mock scan operation to return the stored item
    mock_table.scan.return_value = {
        "Items": [stored_item],
        "Count": 1,
        "ScannedCount": 1,
    }

    with patch("boto3.resource", return_value=mock_dynamodb):
        with patch.dict(os.environ, {"DYNAMODB_TABLE_NAME": "test-table"}):
            version_manager = VersionManager()

            # Store the version
            version_manager.mark_version_processed(release_info)

            # Verify put_item was called with correct data
            mock_table.put_item.assert_called_once()
            put_item_args = mock_table.put_item.call_args[1]["Item"]

            # Verify all required fields are present in storage
            assert put_item_args["version"] == release_info.version
            assert put_item_args["deb_url"] == release_info.deb_url
            assert put_item_args["certificate_url"] == release_info.certificate_url
            assert put_item_args["signature_url"] == release_info.signature_url
            assert put_item_args["pub_date"] == release_info.pub_date
            assert put_item_args["notes"] == release_info.notes
            assert "processed_timestamp" in put_item_args

            # Verify version can be checked for existence
            exists = version_manager.is_version_processed(release_info.version)
            assert exists is True

            # Verify get_item was called with correct key
            mock_table.get_item.assert_called_once_with(
                Key={"version": release_info.version}, ProjectionExpression="version"
            )

            # Verify version appears in processed versions list
            processed_versions = version_manager.get_processed_versions()
            assert release_info.version in processed_versions

            # Verify scan operation was called for retrieving versions
            mock_table.scan.assert_called()

            # Verify all releases can be retrieved with complete information
            all_releases = version_manager.get_all_releases()
            assert len(all_releases) == 1

            retrieved_release = all_releases[0]
            assert retrieved_release.version == release_info.version
            assert retrieved_release.deb_url == release_info.deb_url
            assert retrieved_release.certificate_url == release_info.certificate_url
            assert retrieved_release.signature_url == release_info.signature_url
            assert retrieved_release.pub_date == release_info.pub_date
            assert retrieved_release.notes == release_info.notes
            assert retrieved_release.processed_timestamp is not None

            # Test pagination handling by mocking multiple pages
            mock_table.reset_mock()
            mock_table.scan.side_effect = [
                {
                    "Items": [stored_item],
                    "LastEvaluatedKey": {"version": version},
                },
                {
                    "Items": [],
                    "Count": 0,
                    "ScannedCount": 0,
                },
            ]

            # Should handle pagination correctly
            all_releases_paginated = version_manager.get_all_releases()
            assert len(all_releases_paginated) == 1
            assert mock_table.scan.call_count == 2

            # Verify pagination was handled with ExclusiveStartKey
            second_call_kwargs = mock_table.scan.call_args_list[1][1]
            assert "ExclusiveStartKey" in second_call_kwargs
            assert second_call_kwargs["ExclusiveStartKey"] == {"version": version}
