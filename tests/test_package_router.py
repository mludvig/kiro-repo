"""Unit tests for PackageRouter."""

from unittest.mock import MagicMock, patch

import pytest

from src.config_manager import PackageConfig, SourceConfig
from src.models import PackageMetadata
from src.package_router import PackageRouter

# --- Fixtures ---


@pytest.fixture
def external_source_config() -> SourceConfig:
    """Source config for external_download type."""
    return SourceConfig(
        type="external_download",
        metadata_endpoint="https://example.com/metadata",
    )


@pytest.fixture
def build_script_source_config() -> SourceConfig:
    """Source config for build_script type."""
    return SourceConfig(
        type="build_script",
        staging_prefix="staging/kiro-repo/",
    )


@pytest.fixture
def external_package_config(external_source_config) -> PackageConfig:
    """Package config using external_download source."""
    return PackageConfig(
        package_name="kiro",
        description="Kiro IDE",
        maintainer="Kiro Team <support@kiro.dev>",
        homepage="https://kiro.dev",
        section="editors",
        priority="optional",
        architecture="amd64",
        depends="libgtk-3-0",
        source=external_source_config,
    )


@pytest.fixture
def build_script_package_config(build_script_source_config) -> PackageConfig:
    """Package config using build_script source."""
    return PackageConfig(
        package_name="kiro-repo",
        description="Kiro IDE APT repository configuration",
        maintainer="Kiro Team <support@kiro.dev>",
        homepage="https://kiro.dev",
        section="misc",
        priority="optional",
        architecture="all",
        depends=None,
        source=build_script_source_config,
    )


@pytest.fixture
def sample_metadata() -> PackageMetadata:
    """Sample PackageMetadata for a processed package."""
    return PackageMetadata(
        package_name="kiro",
        version="1.2.0",
        architecture="amd64",
        pub_date="2024-06-01",
        deb_url="https://example.com/kiro_1.2.0_amd64.deb",
        actual_filename="kiro_1.2.0_amd64.deb",
        file_size=50_000_000,
        md5_hash="d41d8cd98f00b204e9800998ecf8427e",
        sha1_hash="da39a3ee5e6b4b0d3255bfef95601890afd80709",
        sha256_hash=(
            "e3b0c44298fc1c149afbf4c8996fb924"
            "27ae41e4649b934ca495991b7852b855"
        ),
        section="editors",
        priority="optional",
        maintainer="Kiro Team <support@kiro.dev>",
        homepage="https://kiro.dev",
        description="Kiro IDE",
        depends="libgtk-3-0",
    )


def _make_router_no_configs() -> PackageRouter:
    """Create a PackageRouter with no configs loaded (empty handlers)."""
    with (
        patch("src.package_router.ConfigManager") as mock_cm,
        patch("src.package_router.VersionManager"),
    ):
        mock_cm.return_value.load_all_configs.return_value = []
        return PackageRouter(config_dir="config/packages")


# --- Handler creation tests ---


class TestCreateHandler:
    """Tests for _create_handler routing to correct handler classes."""

    def test_external_download_creates_kiro_handler(
        self, external_package_config
    ):
        """external_download source type creates KiroPackageHandler."""
        router = _make_router_no_configs()

        with patch("src.package_router.KiroPackageHandler") as mock_cls:
            handler = router._create_handler(external_package_config)

        mock_cls.assert_called_once_with(external_package_config)
        assert handler == mock_cls.return_value

    def test_build_script_creates_kiro_repo_handler(
        self, build_script_package_config
    ):
        """build_script source type creates KiroRepoPackageHandler."""
        router = _make_router_no_configs()

        with patch(
            "src.package_router.KiroRepoPackageHandler"
        ) as mock_cls:
            handler = router._create_handler(build_script_package_config)

        mock_cls.assert_called_once_with(build_script_package_config)
        assert handler == mock_cls.return_value

    def test_github_release_raises_not_implemented(
        self, external_package_config
    ):
        """github_release source type raises ValueError (not yet implemented)."""
        router = _make_router_no_configs()
        external_package_config.source.type = "github_release"

        with pytest.raises(ValueError, match="not yet implemented"):
            router._create_handler(external_package_config)

    def test_unknown_source_type_raises_value_error(
        self, external_package_config
    ):
        """Unknown source type raises ValueError."""
        router = _make_router_no_configs()
        external_package_config.source.type = "ftp_mirror"

        with pytest.raises(ValueError, match="Unknown source type"):
            router._create_handler(external_package_config)


# --- Initialization tests ---


@patch("src.package_router.KiroPackageHandler")
@patch("src.package_router.KiroRepoPackageHandler")
@patch("src.package_router.VersionManager")
@patch("src.package_router.ConfigManager")
class TestInit:
    """Tests for PackageRouter initialization and handler registration."""

    def test_registers_handlers_from_configs(
        self,
        mock_config_manager,
        mock_version_manager,
        mock_repo_handler,
        mock_kiro_handler,
        external_package_config,
        build_script_package_config,
    ):
        """Handlers are registered for each loaded config."""
        mock_config_manager.return_value.load_all_configs.return_value = [
            external_package_config,
            build_script_package_config,
        ]

        router = PackageRouter()

        assert "kiro" in router.handlers
        assert "kiro-repo" in router.handlers
        assert len(router.handlers) == 2

    def test_empty_config_produces_no_handlers(
        self,
        mock_config_manager,
        mock_version_manager,
        mock_repo_handler,
        mock_kiro_handler,
    ):
        """No configs loaded means no handlers registered."""
        mock_config_manager.return_value.load_all_configs.return_value = []

        router = PackageRouter()

        assert router.handlers == {}


# --- process_all_packages tests ---


@patch("src.package_router.VersionManager")
@patch("src.package_router.ConfigManager")
class TestProcessAllPackages:
    """Tests for process_all_packages orchestration logic."""

    def test_returns_newly_processed_packages(
        self,
        mock_config_manager,
        mock_version_manager,
        sample_metadata,
    ):
        """New versions are acquired, stored, and returned."""
        mock_config_manager.return_value.load_all_configs.return_value = []
        mock_vm = mock_version_manager.return_value
        mock_vm.is_package_version_processed.return_value = False

        mock_handler = MagicMock()
        mock_handler.check_new_version.return_value = "1.2.0"
        mock_handler.acquire_package.return_value = sample_metadata

        router = PackageRouter()
        router.handlers = {"kiro": mock_handler}

        results = router.process_all_packages()

        assert len(results) == 1
        assert results[0] is sample_metadata
        mock_handler.acquire_package.assert_called_once_with("1.2.0")
        mock_vm.store_package_metadata.assert_called_once_with(
            sample_metadata
        )

    def test_skips_package_with_no_new_version(
        self,
        mock_config_manager,
        mock_version_manager,
    ):
        """Packages returning None from check_new_version are skipped."""
        mock_config_manager.return_value.load_all_configs.return_value = []

        mock_handler = MagicMock()
        mock_handler.check_new_version.return_value = None

        router = PackageRouter()
        router.handlers = {"kiro": mock_handler}

        results = router.process_all_packages()

        assert results == []
        mock_handler.acquire_package.assert_not_called()

    def test_skips_already_processed_version(
        self,
        mock_config_manager,
        mock_version_manager,
    ):
        """Already-processed versions are not re-acquired."""
        mock_config_manager.return_value.load_all_configs.return_value = []
        mock_vm = mock_version_manager.return_value
        mock_vm.is_package_version_processed.return_value = True

        mock_handler = MagicMock()
        mock_handler.check_new_version.return_value = "1.0.0"

        router = PackageRouter()
        router.handlers = {"kiro": mock_handler}

        results = router.process_all_packages()

        assert results == []
        mock_vm.is_package_version_processed.assert_called_once_with(
            "kiro", "1.0.0"
        )
        mock_handler.acquire_package.assert_not_called()

    def test_stores_metadata_for_new_packages(
        self,
        mock_config_manager,
        mock_version_manager,
        sample_metadata,
    ):
        """version_manager.store_package_metadata is called for new packages."""
        mock_config_manager.return_value.load_all_configs.return_value = []
        mock_vm = mock_version_manager.return_value
        mock_vm.is_package_version_processed.return_value = False

        mock_handler = MagicMock()
        mock_handler.check_new_version.return_value = "1.2.0"
        mock_handler.acquire_package.return_value = sample_metadata

        router = PackageRouter()
        router.handlers = {"kiro": mock_handler}

        router.process_all_packages()

        mock_vm.store_package_metadata.assert_called_once_with(
            sample_metadata
        )


# --- force_rebuild tests ---


@patch("src.package_router.VersionManager")
@patch("src.package_router.ConfigManager")
class TestForceRebuild:
    """Tests for force_rebuild=True behavior."""

    def test_returns_empty_list(
        self,
        mock_config_manager,
        mock_version_manager,
    ):
        """force_rebuild=True returns an empty list immediately."""
        mock_config_manager.return_value.load_all_configs.return_value = []

        mock_handler = MagicMock()
        router = PackageRouter()
        router.handlers = {"kiro": mock_handler}

        results = router.process_all_packages(force_rebuild=True)

        assert results == []

    def test_does_not_call_check_new_version(
        self,
        mock_config_manager,
        mock_version_manager,
    ):
        """force_rebuild=True skips all handler version checks."""
        mock_config_manager.return_value.load_all_configs.return_value = []

        mock_handler = MagicMock()
        router = PackageRouter()
        router.handlers = {"kiro": mock_handler}

        router.process_all_packages(force_rebuild=True)

        mock_handler.check_new_version.assert_not_called()
        mock_handler.acquire_package.assert_not_called()


# --- Error isolation tests ---


@patch("src.package_router.VersionManager")
@patch("src.package_router.ConfigManager")
class TestErrorIsolation:
    """Tests that errors in one handler don't affect others."""

    def test_other_handlers_still_processed_after_failure(
        self,
        mock_config_manager,
        mock_version_manager,
        sample_metadata,
    ):
        """A failing handler does not prevent subsequent handlers from running."""
        mock_config_manager.return_value.load_all_configs.return_value = []
        mock_vm = mock_version_manager.return_value
        mock_vm.is_package_version_processed.return_value = False

        failing_handler = MagicMock()
        failing_handler.check_new_version.side_effect = RuntimeError(
            "API timeout"
        )

        success_metadata = PackageMetadata(
            package_name="kiro-repo",
            version="1.0.0",
            architecture="all",
            pub_date="2024-06-01",
            deb_url="",
            actual_filename="kiro-repo_1.0.0_all.deb",
            file_size=2048,
            md5_hash="abc",
            sha1_hash="def",
            sha256_hash="ghi",
        )
        success_handler = MagicMock()
        success_handler.check_new_version.return_value = "1.0.0"
        success_handler.acquire_package.return_value = success_metadata

        router = PackageRouter()
        # Use dict to guarantee insertion order (Python 3.7+)
        router.handlers = {
            "kiro": failing_handler,
            "kiro-repo": success_handler,
        }

        results = router.process_all_packages()

        assert len(results) == 1
        assert results[0].package_name == "kiro-repo"
        success_handler.acquire_package.assert_called_once_with("1.0.0")

    def test_failed_package_not_in_results(
        self,
        mock_config_manager,
        mock_version_manager,
    ):
        """A handler that raises is excluded from the results list."""
        mock_config_manager.return_value.load_all_configs.return_value = []
        mock_vm = mock_version_manager.return_value
        mock_vm.is_package_version_processed.return_value = False

        failing_handler = MagicMock()
        failing_handler.check_new_version.return_value = "2.0.0"
        failing_handler.acquire_package.side_effect = Exception(
            "download failed"
        )

        router = PackageRouter()
        router.handlers = {"kiro": failing_handler}

        results = router.process_all_packages()

        assert results == []
        mock_vm.store_package_metadata.assert_not_called()


# --- cleanup_downloads tests ---


@patch("src.package_router.VersionManager")
@patch("src.package_router.ConfigManager")
class TestCleanupDownloads:
    """Tests for cleanup_downloads temporary file removal."""

    @patch("src.package_router.os.remove")
    @patch(
        "src.package_router.glob.glob",
        side_effect=[
            ["/tmp/kiro_1.0.deb"],
            ["/tmp/kiro.cert"],
            ["/tmp/kiro.sig"],
        ],
    )
    def test_removes_matching_files(
        self,
        mock_glob,
        mock_remove,
        mock_config_manager,
        mock_version_manager,
    ):
        """All matched temp files are removed."""
        mock_config_manager.return_value.load_all_configs.return_value = []

        router = PackageRouter()
        router.cleanup_downloads()

        assert mock_remove.call_count == 3
        mock_remove.assert_any_call("/tmp/kiro_1.0.deb")
        mock_remove.assert_any_call("/tmp/kiro.cert")
        mock_remove.assert_any_call("/tmp/kiro.sig")

    @patch("src.package_router.os.remove", side_effect=OSError("busy"))
    @patch(
        "src.package_router.glob.glob",
        side_effect=[["/tmp/locked.deb"], [], []],
    )
    def test_handles_os_error_gracefully(
        self,
        mock_glob,
        mock_remove,
        mock_config_manager,
        mock_version_manager,
    ):
        """OSError during file removal is caught and does not propagate."""
        mock_config_manager.return_value.load_all_configs.return_value = []

        router = PackageRouter()
        # Should not raise
        router.cleanup_downloads()

        mock_remove.assert_called_once_with("/tmp/locked.deb")

    @patch("src.package_router.os.remove")
    @patch(
        "src.package_router.glob.glob",
        side_effect=[[], [], []],
    )
    def test_no_files_to_clean(
        self,
        mock_glob,
        mock_remove,
        mock_config_manager,
        mock_version_manager,
    ):
        """No-op when no temp files match the patterns."""
        mock_config_manager.return_value.load_all_configs.return_value = []

        router = PackageRouter()
        router.cleanup_downloads()

        mock_remove.assert_not_called()
