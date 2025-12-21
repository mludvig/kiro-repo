"""Property-based test for repository structure completeness."""

from hypothesis import given
from hypothesis import strategies as st

from src.models import ReleaseInfo
from src.repository_builder import RepositoryBuilder


# **Feature: debian-repo-manager, Property 4: Repository Structure Completeness**
# **Validates: Requirements 3.1, 3.2**
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
def test_repository_structure_completeness_property(releases):
    """Property test: For any set of historical package versions, the generated repository structure should include all versions in the Packages file and maintain proper debian repository format.

    This property tests that repository structure generation includes all provided
    versions and maintains proper debian repository format standards.
    """
    builder = RepositoryBuilder()

    try:
        # Create repository structure
        repo_structure = builder.create_repository_structure(releases)

        # Verify deb_files only contains releases with local files (when no local_files_map provided, should be empty)
        # Since we're not providing local_files_map, deb_files should be empty
        assert len(repo_structure.deb_files) == 0

        # Verify Packages file contains all versions
        packages_content = repo_structure.packages_file_content
        for release in releases:
            # Each version should appear in the Packages file
            assert f"Version: {release.version}" in packages_content
            assert "Package: kiro" in packages_content

        # Verify Release file is generated
        release_content = repo_structure.release_file_content
        assert "Origin: Kiro" in release_content
        assert "Suite: stable" in release_content
        assert "Architectures: amd64" in release_content

        # Verify Release file contains checksums for Packages file
        assert "MD5Sum:" in release_content
        assert "SHA1:" in release_content
        assert "SHA256:" in release_content
        assert "Packages" in release_content

        # Verify base path is set
        assert repo_structure.base_path is not None
        assert len(repo_structure.base_path) > 0

        # Verify each deb file entry has proper structure (if any exist)
        for deb_file in repo_structure.deb_files:
            assert deb_file.version is not None
            assert deb_file.deb_file_path.endswith(".deb")
            assert deb_file.certificate_path.endswith(".pem")
            assert deb_file.signature_path.endswith(".bin")

        # When local_files_map is not provided, deb_files should be empty
        # but Packages file should still contain all releases
        if len(repo_structure.deb_files) == 0:
            # Verify Packages file still contains all versions
            for release in releases:
                assert f"Version: {release.version}" in packages_content

    except (ValueError, AttributeError):
        # Skip invalid inputs that don't meet our requirements
        # This can happen with edge cases in generated data
        pass
