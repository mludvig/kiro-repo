"""Unit tests for KiroPackageHandler."""

from unittest.mock import patch

import pytest
import requests

from src.config_manager import PackageConfig, SourceConfig
from src.models import LocalReleaseFiles, PackageMetadata, ReleaseInfo
from src.package_handlers.kiro_handler import KiroPackageHandler


@pytest.fixture
def source_config():
    return SourceConfig(
        type="external_download",
        metadata_endpoint="https://custom.endpoint/metadata.json",
    )


@pytest.fixture
def package_config(source_config):
    return PackageConfig(
        package_name="kiro",
        description="Kiro IDE - AI-powered development environment",
        maintainer="Kiro Team <support@kiro.dev>",
        homepage="https://kiro.dev",
        section="editors",
        priority="optional",
        architecture="amd64",
        depends="libnss3 (>= 3.0)",
        source=source_config,
    )


@pytest.fixture
def release_info():
    return ReleaseInfo(
        version="1.2.3",
        pub_date="2024-01-15",
        deb_url="https://download.example.com/kiro_1.2.3_amd64.deb",
        certificate_url="https://download.example.com/certificate.pem",
        signature_url="https://download.example.com/signature.bin",
        notes="Bug fixes and improvements",
    )


@pytest.fixture
def local_files():
    return LocalReleaseFiles(
        deb_file_path="/tmp/kiro-1.2.3/kiro_1.2.3_amd64.deb",
        certificate_path="/tmp/kiro-1.2.3/certificate.pem",
        signature_path="/tmp/kiro-1.2.3/signature.bin",
        version="1.2.3",
    )


@patch("src.package_handlers.kiro_handler.PackageDownloader")
@patch("src.package_handlers.kiro_handler.MetadataClient")
class TestKiroPackageHandler:
    """Tests for KiroPackageHandler covering init, version check,
    package acquisition, error handling, and file path generation."""

    def test_init_sets_metadata_url_from_config(
        self, mock_metadata_cls, mock_downloader_cls, package_config
    ):
        KiroPackageHandler(package_config)
        mock_metadata_cls.assert_called_once_with(
            metadata_url="https://custom.endpoint/metadata.json"
        )

    def test_init_raises_when_no_endpoint(
        self, mock_metadata_cls, mock_downloader_cls, package_config
    ):
        package_config.source.metadata_endpoint = None
        with pytest.raises(ValueError, match="metadata_endpoint"):
            KiroPackageHandler(package_config)

    def test_check_new_version_returns_version(
        self,
        mock_metadata_cls,
        mock_downloader_cls,
        package_config,
        release_info,
    ):
        mock_client = mock_metadata_cls.return_value
        mock_client.get_current_release.return_value = release_info
        handler = KiroPackageHandler(package_config)
        result = handler.check_new_version()
        assert result == "1.2.3"
        mock_client.get_current_release.assert_called_once()

    def test_check_new_version_returns_none_on_error(
        self, mock_metadata_cls, mock_downloader_cls, package_config
    ):
        mock_client = mock_metadata_cls.return_value
        mock_client.get_current_release.side_effect = (
            requests.RequestException("connection failed")
        )
        handler = KiroPackageHandler(package_config)
        result = handler.check_new_version()
        assert result is None

    def test_acquire_package_returns_complete_metadata(
        self,
        mock_metadata_cls,
        mock_downloader_cls,
        package_config,
        release_info,
        local_files,
    ):
        mock_client = mock_metadata_cls.return_value
        mock_client.get_current_release.return_value = release_info

        mock_dl = mock_downloader_cls.return_value
        mock_dl.download_release_files.return_value = local_files

        def populate_side_effect(ri, lf):
            ri.actual_filename = "kiro_1.2.3_amd64.deb"
            ri.file_size = 98765432
            ri.md5_hash = "d41d8cd98f00b204e9800998ecf8427e"
            ri.sha1_hash = (
                "da39a3ee5e6b4b0d3255bfef95601890afd80709"
            )
            ri.sha256_hash = (
                "e3b0c44298fc1c149afbf4c8996fb924"
                "27ae41e4649b934ca495991b7852b855"
            )

        mock_dl.populate_file_metadata.side_effect = (
            populate_side_effect
        )

        handler = KiroPackageHandler(package_config)
        metadata = handler.acquire_package("1.2.3")

        assert isinstance(metadata, PackageMetadata)
        assert metadata.package_name == "kiro"
        assert metadata.version == "1.2.3"
        assert metadata.architecture == "amd64"
        assert metadata.pub_date == "2024-01-15"
        assert metadata.deb_url == release_info.deb_url
        assert metadata.actual_filename == "kiro_1.2.3_amd64.deb"
        assert metadata.file_size == 98765432
        assert (
            metadata.md5_hash
            == "d41d8cd98f00b204e9800998ecf8427e"
        )
        assert (
            metadata.sha1_hash
            == "da39a3ee5e6b4b0d3255bfef95601890afd80709"
        )
        assert metadata.sha256_hash == (
            "e3b0c44298fc1c149afbf4c8996fb924"
            "27ae41e4649b934ca495991b7852b855"
        )
        assert (
            metadata.certificate_url
            == release_info.certificate_url
        )
        assert (
            metadata.signature_url == release_info.signature_url
        )
        assert metadata.notes == "Bug fixes and improvements"

        mock_dl.download_release_files.assert_called_once_with(
            release_info
        )
        mock_dl.verify_package_integrity.assert_called_once_with(
            local_files
        )
        mock_dl.populate_file_metadata.assert_called_once_with(
            release_info, local_files
        )

    def test_acquire_package_uses_config_fields(
        self,
        mock_metadata_cls,
        mock_downloader_cls,
        package_config,
        release_info,
        local_files,
    ):
        mock_client = mock_metadata_cls.return_value
        mock_client.get_current_release.return_value = release_info

        mock_dl = mock_downloader_cls.return_value
        mock_dl.download_release_files.return_value = local_files

        def populate_side_effect(ri, lf):
            ri.actual_filename = "kiro_1.2.3_amd64.deb"
            ri.file_size = 100
            ri.md5_hash = "abc"
            ri.sha1_hash = "def"
            ri.sha256_hash = "ghi"

        mock_dl.populate_file_metadata.side_effect = (
            populate_side_effect
        )

        handler = KiroPackageHandler(package_config)
        metadata = handler.acquire_package("1.2.3")

        assert metadata.section == "editors"
        assert metadata.priority == "optional"
        assert (
            metadata.maintainer
            == "Kiro Team <support@kiro.dev>"
        )
        assert metadata.homepage == "https://kiro.dev"
        assert (
            metadata.description
            == "Kiro IDE - AI-powered development environment"
        )
        assert metadata.depends == "libnss3 (>= 3.0)"

    def test_acquire_package_raises_on_download_failure(
        self,
        mock_metadata_cls,
        mock_downloader_cls,
        package_config,
        release_info,
    ):
        mock_client = mock_metadata_cls.return_value
        mock_client.get_current_release.return_value = release_info

        mock_dl = mock_downloader_cls.return_value
        mock_dl.download_release_files.side_effect = (
            requests.RequestException("download failed")
        )

        handler = KiroPackageHandler(package_config)
        with pytest.raises(
            requests.RequestException, match="download"
        ):
            handler.acquire_package("1.2.3")

    def test_acquire_package_raises_on_integrity_failure(
        self,
        mock_metadata_cls,
        mock_downloader_cls,
        package_config,
        release_info,
        local_files,
    ):
        mock_client = mock_metadata_cls.return_value
        mock_client.get_current_release.return_value = release_info

        mock_dl = mock_downloader_cls.return_value
        mock_dl.download_release_files.return_value = local_files
        mock_dl.verify_package_integrity.side_effect = (
            ValueError("checksum mismatch")
        )

        handler = KiroPackageHandler(package_config)
        with pytest.raises(ValueError, match="checksum"):
            handler.acquire_package("1.2.3")

    def test_get_package_file_path(
        self,
        mock_metadata_cls,
        mock_downloader_cls,
        package_config,
    ):
        handler = KiroPackageHandler(package_config)
        metadata = PackageMetadata(
            package_name="kiro",
            version="1.2.3",
            architecture="amd64",
            pub_date="2024-01-15",
            deb_url="https://example.com/kiro.deb",
            actual_filename="kiro_1.2.3_amd64.deb",
            file_size=100,
            md5_hash="abc",
            sha1_hash="def",
            sha256_hash="ghi",
        )
        path = handler.get_package_file_path(metadata)
        assert path == "/tmp/kiro-1.2.3/kiro_1.2.3_amd64.deb"
