"""Unit tests for metadata validation logging in RepositoryBuilder (Requirement 14.6)."""

import logging

import pytest

from src.models import PackageMetadata
from src.repository_builder import RepositoryBuilder


def _make_complete_package(**overrides) -> PackageMetadata:
    """Return a fully-populated PackageMetadata, with optional field overrides."""
    defaults = dict(
        package_name="kiro",
        version="1.0.0",
        architecture="amd64",
        pub_date="2024-01-01",
        deb_url="https://example.com/kiro_1.0.0_amd64.deb",
        actual_filename="kiro_1.0.0_amd64.deb",
        file_size=50_000_000,
        md5_hash="d41d8cd98f00b204e9800998ecf8427e",
        sha1_hash="da39a3ee5e6b4b0d3255bfef95601890afd80709",
        sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        section="editors",
        priority="optional",
        maintainer="Kiro Team <support@kiro.dev>",
        homepage="https://kiro.dev",
        description="Kiro IDE",
    )
    defaults.update(overrides)
    return PackageMetadata(**defaults)


class TestValidatePackageMetadata:
    """Tests for RepositoryBuilder.validate_package_metadata."""

    def test_complete_metadata_returns_no_missing_fields(self):
        """A fully-populated package has no missing fields."""
        builder = RepositoryBuilder()
        pkg = _make_complete_package()
        assert builder.validate_package_metadata(pkg) == []

    def test_missing_version_is_reported(self):
        """An empty version string is flagged as missing."""
        builder = RepositoryBuilder()
        pkg = _make_complete_package(version="")
        missing = builder.validate_package_metadata(pkg)
        assert "version" in missing

    def test_missing_package_name_is_reported(self):
        """An empty package_name is flagged as missing."""
        builder = RepositoryBuilder()
        pkg = _make_complete_package(package_name="")
        missing = builder.validate_package_metadata(pkg)
        assert "package_name" in missing

    def test_zero_file_size_is_reported(self):
        """A file_size of 0 is treated as missing."""
        builder = RepositoryBuilder()
        pkg = _make_complete_package(file_size=0)
        missing = builder.validate_package_metadata(pkg)
        assert "file_size" in missing

    def test_empty_hash_fields_are_reported(self):
        """Empty hash strings are flagged as missing."""
        builder = RepositoryBuilder()
        pkg = _make_complete_package(md5_hash="", sha1_hash="", sha256_hash="")
        missing = builder.validate_package_metadata(pkg)
        assert "md5_hash" in missing
        assert "sha1_hash" in missing
        assert "sha256_hash" in missing

    def test_multiple_missing_fields_all_reported(self):
        """All missing fields are returned, not just the first one."""
        builder = RepositoryBuilder()
        pkg = _make_complete_package(
            version="", actual_filename="", maintainer=""
        )
        missing = builder.validate_package_metadata(pkg)
        assert "version" in missing
        assert "actual_filename" in missing
        assert "maintainer" in missing

    def test_empty_description_is_reported(self):
        """An empty description is flagged as missing."""
        builder = RepositoryBuilder()
        pkg = _make_complete_package(description="")
        missing = builder.validate_package_metadata(pkg)
        assert "description" in missing


class TestGeneratePackagesFileSkipsIncomplete:
    """Tests that generate_packages_file skips packages with incomplete metadata."""

    def test_complete_package_is_included(self):
        """A package with all required fields appears in the Packages file."""
        builder = RepositoryBuilder()
        pkg = _make_complete_package()
        content = builder.generate_packages_file([pkg])
        assert "Package: kiro" in content
        assert "Version: 1.0.0" in content

    def test_package_with_missing_version_is_skipped(self):
        """A package missing version is excluded from the Packages file."""
        builder = RepositoryBuilder()
        pkg = _make_complete_package(version="")
        content = builder.generate_packages_file([pkg])
        assert "Package: kiro" not in content

    def test_package_with_missing_hash_is_skipped(self):
        """A package with empty hashes is excluded from the Packages file."""
        builder = RepositoryBuilder()
        pkg = _make_complete_package(md5_hash="", sha1_hash="", sha256_hash="")
        content = builder.generate_packages_file([pkg])
        assert "Package: kiro" not in content

    def test_valid_packages_included_when_some_are_invalid(self):
        """Valid packages are still included even when others are skipped."""
        builder = RepositoryBuilder()
        valid_pkg = _make_complete_package(package_name="kiro", version="1.0.0")
        invalid_pkg = _make_complete_package(
            package_name="kiro-repo", version="", actual_filename=""
        )
        content = builder.generate_packages_file([valid_pkg, invalid_pkg])
        assert "Package: kiro" in content
        assert "Package: kiro-repo" not in content

    def test_all_invalid_packages_returns_empty_content(self):
        """When all packages are invalid, a minimal (non-crashing) result is returned."""
        builder = RepositoryBuilder()
        pkg = _make_complete_package(version="", actual_filename="")
        content = builder.generate_packages_file([pkg])
        # Should not raise; content should be essentially empty
        assert "Package:" not in content


class TestMetadataValidationLogging:
    """Tests that appropriate log messages are emitted for incomplete metadata."""

    def test_warning_logged_when_package_skipped(self, caplog):
        """A WARNING is logged when a package is skipped due to missing metadata."""
        builder = RepositoryBuilder()
        pkg = _make_complete_package(version="")

        with caplog.at_level(logging.WARNING, logger="src.repository_builder"):
            builder.generate_packages_file([pkg])

        assert any("Skipping package" in r.message for r in caplog.records)

    def test_log_includes_package_name(self, caplog):
        """The warning log includes the package name."""
        builder = RepositoryBuilder()
        pkg = _make_complete_package(package_name="kiro", version="")

        with caplog.at_level(logging.WARNING, logger="src.repository_builder"):
            builder.generate_packages_file([pkg])

        combined = " ".join(r.message for r in caplog.records)
        assert "kiro" in combined

    def test_log_includes_missing_field_names(self, caplog):
        """The warning log names the specific missing fields."""
        builder = RepositoryBuilder()
        pkg = _make_complete_package(version="", md5_hash="")

        with caplog.at_level(logging.WARNING, logger="src.repository_builder"):
            builder.generate_packages_file([pkg])

        combined = " ".join(r.message for r in caplog.records)
        assert "version" in combined
        assert "md5_hash" in combined

    def test_no_warning_logged_for_complete_package(self, caplog):
        """No skip warning is logged when all metadata is present."""
        builder = RepositoryBuilder()
        pkg = _make_complete_package()

        with caplog.at_level(logging.WARNING, logger="src.repository_builder"):
            builder.generate_packages_file([pkg])

        skip_warnings = [r for r in caplog.records if "Skipping package" in r.message]
        assert skip_warnings == []
