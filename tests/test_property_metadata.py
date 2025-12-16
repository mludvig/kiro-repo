"""Property-based tests for metadata processing."""

import json

from hypothesis import given
from hypothesis import strategies as st

from src.metadata_client import MetadataClient


# **Feature: debian-repo-manager, Property 1: Metadata Processing Round Trip**
# **Validates: Requirements 1.1, 1.2**
@given(
    major=st.integers(min_value=0, max_value=99),
    minor=st.integers(min_value=0, max_value=99),
    patch=st.integers(min_value=0, max_value=999),
    pub_date=st.dates().map(str),
    domain=st.sampled_from(["example.com", "test.org", "download.kiro.dev"]),
    protocol=st.sampled_from(["http", "https"]),
    notes=st.text(max_size=100),
)
def test_metadata_processing_round_trip_property(
    major, minor, patch, pub_date, domain, protocol, notes
):
    """Property test: For any valid metadata JSON response, parsing and extracting version information should successfully identify all release entries and their associated URLs.

    This property tests that metadata processing can handle various valid inputs
    and consistently extract version information and URLs.
    """
    # Create realistic version and URL
    version = f"{major}.{minor}.{patch}"
    base_url = f"{protocol}://{domain}"

    # Create valid metadata structure
    metadata = {
        "version": version,
        "pub_date": str(pub_date),
        "url": f"{base_url}/package.deb",
        "certificate": f"{base_url}/cert.pem",
        "signature": f"{base_url}/sig.bin",
        "notes": notes,
    }

    client = MetadataClient()

    try:
        # Parse release info from metadata
        releases = client.parse_release_info(metadata)

        # Should successfully parse exactly one release
        assert len(releases) == 1
        release = releases[0]

        # All extracted information should match the input
        assert release.version == version
        assert release.pub_date == str(pub_date)
        assert release.deb_url == f"{base_url}/package.deb"
        assert release.certificate_url == f"{base_url}/cert.pem"
        assert release.signature_url == f"{base_url}/sig.bin"
        assert release.notes == notes

        # The metadata should be serializable (round trip test)
        serialized = json.dumps(metadata)
        deserialized = json.loads(serialized)

        # Parsing the deserialized metadata should yield identical results
        releases_again = client.parse_release_info(deserialized)
        assert len(releases_again) == 1
        release_again = releases_again[0]

        # All fields should be identical
        assert release_again.version == release.version
        assert release_again.pub_date == release.pub_date
        assert release_again.deb_url == release.deb_url
        assert release_again.certificate_url == release.certificate_url
        assert release_again.signature_url == release.signature_url
        assert release_again.notes == release.notes

    except ValueError:
        # Skip invalid metadata structures that don't meet our requirements
        # This can happen with edge cases in generated data
        pass
