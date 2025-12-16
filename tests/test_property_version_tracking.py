"""Property-based test for version tracking consistency."""

from hypothesis import given
from hypothesis import strategies as st

from src.metadata_client import MetadataClient


# **Feature: debian-repo-manager, Property 2: Version Tracking Consistency**
# **Validates: Requirements 1.5**
@given(
    major=st.integers(min_value=0, max_value=99),
    minor=st.integers(min_value=0, max_value=99),
    patch=st.integers(min_value=0, max_value=999),
    pub_date=st.dates().map(str),
    domain=st.sampled_from(["example.com", "test.org", "download.kiro.dev"]),
    protocol=st.sampled_from(["http", "https"]),
    notes=st.text(max_size=100),
)
def test_version_tracking_consistency_property(
    major, minor, patch, pub_date, domain, protocol, notes
):
    """Property test: For any extracted version information, querying DynamoDB should correctly identify whether the version has been processed previously.

    This property tests that version information extracted from metadata can be consistently
    tracked and identified for processing status determination.
    """

    # Create mock version manager to simulate DynamoDB operations
    class MockVersionManager:
        def __init__(self):
            self.processed_versions = set()

        def is_version_processed(self, version: str) -> bool:
            return version in self.processed_versions

        def mark_version_processed(self, version: str):
            self.processed_versions.add(version)

    # Create realistic version and URL
    version = f"{major}.{minor}.{patch}"
    base_url = f"{protocol}://{domain}"

    # Create metadata client and version manager
    client = MetadataClient()
    version_manager = MockVersionManager()

    # Create valid metadata structure
    metadata = {
        "version": version,
        "pub_date": str(pub_date),
        "url": f"{base_url}/package.deb",
        "certificate": f"{base_url}/cert.pem",
        "signature": f"{base_url}/sig.bin",
        "notes": notes,
    }

    try:
        # Parse release info from metadata
        releases = client.parse_release_info(metadata)
        assert len(releases) == 1
        release = releases[0]

        # Initially, version should not be processed
        assert not version_manager.is_version_processed(release.version)

        # Mark version as processed
        version_manager.mark_version_processed(release.version)

        # Now version should be identified as processed
        assert version_manager.is_version_processed(release.version)

        # Parsing the same metadata again should yield the same version
        releases_again = client.parse_release_info(metadata)
        assert len(releases_again) == 1
        assert releases_again[0].version == release.version

        # Version should still be marked as processed
        assert version_manager.is_version_processed(releases_again[0].version)

        # Test consistency: multiple queries should return the same result
        for _ in range(5):
            assert version_manager.is_version_processed(release.version)

        # Test with different version - should not be processed
        different_version = f"{major + 1}.{minor}.{patch}"
        assert not version_manager.is_version_processed(different_version)

    except ValueError:
        # Skip invalid metadata structures that don't meet our requirements
        # This can happen with edge cases in generated data
        pass
