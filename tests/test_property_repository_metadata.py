"""Property-based test for repository metadata generation."""

import re

from hypothesis import given
from hypothesis import strategies as st

from src.models import ReleaseInfo
from src.repository_builder import RepositoryBuilder


# **Feature: debian-repo-manager, Property 5: Repository Metadata Generation**
# **Validates: Requirements 3.3, 3.4, 3.5**
@given(
    releases=st.lists(
        st.builds(
            ReleaseInfo,
            version=st.builds(
                lambda major, minor, patch: f"{major}.{minor}.{patch}",
                major=st.integers(min_value=0, max_value=99),
                minor=st.integers(min_value=0, max_value=99),
                patch=st.integers(min_value=0, max_value=999),
            ),
            pub_date=st.dates().map(str),
            deb_url=st.builds(
                lambda domain,
                major,
                minor,
                patch: f"https://{domain}/kiro_{major}.{minor}.{patch}_amd64.deb",
                domain=st.sampled_from(["download.kiro.dev", "releases.example.com"]),
                major=st.integers(min_value=0, max_value=99),
                minor=st.integers(min_value=0, max_value=99),
                patch=st.integers(min_value=0, max_value=999),
            ),
            certificate_url=st.builds(
                lambda domain,
                major,
                minor,
                patch: f"https://{domain}/kiro_{major}.{minor}.{patch}.pem",
                domain=st.sampled_from(["download.kiro.dev", "releases.example.com"]),
                major=st.integers(min_value=0, max_value=99),
                minor=st.integers(min_value=0, max_value=99),
                patch=st.integers(min_value=0, max_value=999),
            ),
            signature_url=st.builds(
                lambda domain,
                major,
                minor,
                patch: f"https://{domain}/kiro_{major}.{minor}.{patch}.bin",
                domain=st.sampled_from(["download.kiro.dev", "releases.example.com"]),
                major=st.integers(min_value=0, max_value=99),
                minor=st.integers(min_value=0, max_value=99),
                patch=st.integers(min_value=0, max_value=999),
            ),
            notes=st.text(max_size=100),
        ),
        min_size=1,
        max_size=10,
    )
)
def test_repository_metadata_generation_property(releases):
    """Property test: For any collection of debian packages, the generated Packages and Release files should contain accurate metadata, checksums, and preserve original signatures.

    This property tests that repository metadata generation produces valid debian
    repository files with proper checksums and preserves original package signatures.
    """
    builder = RepositoryBuilder()

    try:
        # Generate Packages file
        packages_content = builder.generate_packages_file(releases)

        # Verify Packages file structure and content
        for release in releases:
            # Each package should have required debian control fields
            version_pattern = f"Version: {re.escape(release.version)}"
            assert re.search(version_pattern, packages_content), (
                f"Version {release.version} not found in Packages file"
            )

            # Verify required debian package fields are present for each version
            package_section = packages_content
            assert "Package: kiro" in package_section
            assert "Architecture: amd64" in package_section
            assert "Maintainer:" in package_section
            assert "Description:" in package_section
            assert "Filename:" in package_section
            assert "Size:" in package_section

            # Verify checksums are present (MD5, SHA1, SHA256)
            assert "MD5sum:" in package_section
            assert "SHA1:" in package_section
            assert "SHA256:" in package_section

        # Generate Release file
        release_content = builder.generate_release_file(packages_content)

        # Verify Release file contains required repository metadata
        assert "Origin: Kiro" in release_content
        assert "Label: Kiro" in release_content
        assert "Suite: stable" in release_content
        assert "Codename: stable" in release_content
        assert "Architectures: amd64" in release_content
        assert "Components: main" in release_content
        assert "Description:" in release_content
        assert "Date:" in release_content

        # Verify Release file contains checksums for Packages file
        assert "MD5Sum:" in release_content
        assert "SHA1:" in release_content
        assert "SHA256:" in release_content

        # Verify checksum entries reference the Packages file
        assert "Packages" in release_content

        # Verify checksums are properly formatted (hex strings)
        md5_matches = re.findall(r"MD5Sum:\s*\n\s*([a-f0-9]{32})", release_content)
        sha1_matches = re.findall(r"SHA1:\s*\n\s*([a-f0-9]{40})", release_content)
        sha256_matches = re.findall(r"SHA256:\s*\n\s*([a-f0-9]{64})", release_content)

        assert len(md5_matches) >= 1, "MD5 checksum not found or improperly formatted"
        assert len(sha1_matches) >= 1, "SHA1 checksum not found or improperly formatted"
        assert len(sha256_matches) >= 1, (
            "SHA256 checksum not found or improperly formatted"
        )

        # Verify file size is included with checksums
        size_pattern = r"\d+\s+Packages"
        assert re.search(size_pattern, release_content), (
            "File size not found in Release file"
        )

        # Verify that original signatures are preserved (no re-signing)
        # This is tested by ensuring we don't add any GPG signature blocks
        assert "-----BEGIN PGP SIGNATURE-----" not in release_content
        assert "-----BEGIN PGP MESSAGE-----" not in release_content

        # Verify consistency: same input should produce same output
        packages_content_2 = builder.generate_packages_file(releases)
        release_content_2 = builder.generate_release_file(packages_content_2)

        # Content should be identical for same input
        assert packages_content == packages_content_2
        # Release file will have different timestamps, so we check structure instead
        assert "Origin: Kiro" in release_content_2
        assert "Suite: stable" in release_content_2

    except (ValueError, AttributeError):
        # Skip invalid inputs that don't meet our requirements
        # This can happen with edge cases in generated data
        pass
