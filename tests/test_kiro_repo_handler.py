"""Unit tests for KiroRepoPackageHandler."""

from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError

from src.config_manager import PackageConfig, SourceConfig
from src.models import PackageMetadata
from src.package_handlers.kiro_repo_handler import KiroRepoPackageHandler


@pytest.fixture
def source_config():
    return SourceConfig(
        type="build_script",
        staging_prefix="staging/kiro-repo/",
    )


@pytest.fixture
def package_config(source_config):
    return PackageConfig(
        package_name="kiro-repo",
        description="Kiro IDE APT repository configuration",
        maintainer="Kiro Team <support@kiro.dev>",
        homepage="https://kiro.dev",
        section="misc",
        priority="optional",
        architecture="all",
        depends=None,
        source=source_config,
    )


@pytest.fixture
def package_metadata():
    return PackageMetadata(
        package_name="kiro-repo",
        version="1.0.0",
        architecture="all",
        pub_date="2024-01-15",
        deb_url="",
        actual_filename="kiro-repo_1.0.0_all.deb",
        file_size=2048,
        md5_hash="d41d8cd98f00b204e9800998ecf8427e",
        sha1_hash="da39a3ee5e6b4b0d3255bfef95601890afd80709",
        sha256_hash=(
            "e3b0c44298fc1c149afbf4c8996fb924"
            "27ae41e4649b934ca495991b7852b855"
        ),
        section="misc",
        priority="optional",
        maintainer="Kiro Team <support@kiro.dev>",
        homepage="https://kiro.dev",
        description="Kiro IDE APT repository configuration",
    )


@patch(
    "src.package_handlers.kiro_repo_handler.get_env_var",
    return_value="my-test-bucket",
)
@patch("src.package_handlers.kiro_repo_handler.boto3")
class TestKiroRepoPackageHandler:
    """Tests for KiroRepoPackageHandler covering version check,
    acquire, and S3 staging download."""

    def test_check_new_version_returns_none(
        self, mock_boto3, mock_get_env_var, package_config
    ):
        handler = KiroRepoPackageHandler(package_config)
        result = handler.check_new_version()
        assert result is None

    def test_acquire_package_raises_not_implemented(
        self, mock_boto3, mock_get_env_var, package_config
    ):
        handler = KiroRepoPackageHandler(package_config)
        with pytest.raises(
            NotImplementedError,
            match="kiro-repo packages are stored by build script",
        ):
            handler.acquire_package("1.0.0")

    def test_get_package_file_path_downloads_from_staging(
        self,
        mock_boto3,
        mock_get_env_var,
        package_config,
        package_metadata,
    ):
        mock_s3 = mock_boto3.client.return_value
        handler = KiroRepoPackageHandler(package_config)

        path = handler.get_package_file_path(package_metadata)

        assert path == "/tmp/kiro-repo_1.0.0_all.deb"
        mock_s3.download_file.assert_called_once_with(
            "my-test-bucket",
            "staging/kiro-repo/kiro-repo_1.0.0_all.deb",
            "/tmp/kiro-repo_1.0.0_all.deb",
        )

    def test_get_package_file_path_uses_staging_prefix(
        self,
        mock_boto3,
        mock_get_env_var,
        package_config,
        package_metadata,
    ):
        package_config.source.staging_prefix = "custom/prefix/"
        mock_s3 = mock_boto3.client.return_value
        handler = KiroRepoPackageHandler(package_config)

        handler.get_package_file_path(package_metadata)

        mock_s3.download_file.assert_called_once_with(
            "my-test-bucket",
            "custom/prefix/kiro-repo_1.0.0_all.deb",
            "/tmp/kiro-repo_1.0.0_all.deb",
        )

    def test_get_package_file_path_raises_on_s3_error(
        self,
        mock_boto3,
        mock_get_env_var,
        package_config,
        package_metadata,
    ):
        mock_s3 = mock_boto3.client.return_value
        mock_s3.download_file.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Not found"}},
            "GetObject",
        )
        handler = KiroRepoPackageHandler(package_config)

        with pytest.raises(ClientError):
            handler.get_package_file_path(package_metadata)
