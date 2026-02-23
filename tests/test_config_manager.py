"""Unit tests for config_manager module."""

import pytest
from pathlib import Path
import tempfile
import textwrap

from src.config_manager import ConfigManager, PackageConfig, SourceConfig


KIRO_YAML = textwrap.dedent("""\
    package_name: kiro
    description: "Kiro IDE - AI-powered development environment"
    maintainer: "Kiro Team <support@kiro.dev>"
    homepage: "https://kiro.dev"
    section: editors
    priority: optional
    architecture: amd64
    source:
      type: external_download
      metadata_endpoint: "https://download.kiro.dev/linux/metadata.json"
""")

KIRO_REPO_YAML = textwrap.dedent("""\
    package_name: kiro-repo
    description: "Kiro IDE Repository Configuration"
    maintainer: "Kiro Team <support@kiro.dev>"
    homepage: "https://kiro.dev"
    section: misc
    priority: optional
    architecture: all
    source:
      type: build_script
      staging_prefix: "staging/kiro-repo/"
""")

KIRO_CLI_YAML = textwrap.dedent("""\
    package_name: kiro-cli
    description: "Kiro CLI - Command-line tools for Kiro IDE"
    maintainer: "Kiro Team <support@kiro.dev>"
    homepage: "https://kiro.dev"
    section: devel
    priority: optional
    architecture: amd64
    depends: "kiro (>= 1.0)"
    source:
      type: github_release
      repository: "kiro-dev/kiro-cli"
      asset_pattern: "kiro-cli_*_amd64.deb"
""")


@pytest.fixture
def config_dir(tmp_path):
    """Create a temporary config directory with sample YAML files."""
    (tmp_path / "kiro.yaml").write_text(KIRO_YAML)
    (tmp_path / "kiro-repo.yaml").write_text(KIRO_REPO_YAML)
    return tmp_path


class TestPackageConfigFromYaml:
    def test_loads_kiro_config(self, config_dir):
        config = PackageConfig.from_yaml(config_dir / "kiro.yaml")
        assert config.package_name == "kiro"
        assert config.description == "Kiro IDE - AI-powered development environment"
        assert config.maintainer == "Kiro Team <support@kiro.dev>"
        assert config.homepage == "https://kiro.dev"
        assert config.section == "editors"
        assert config.priority == "optional"
        assert config.architecture == "amd64"
        assert config.depends is None

    def test_loads_source_config_external_download(self, config_dir):
        config = PackageConfig.from_yaml(config_dir / "kiro.yaml")
        assert config.source.type == "external_download"
        assert config.source.metadata_endpoint == "https://download.kiro.dev/linux/metadata.json"
        assert config.source.staging_prefix is None
        assert config.source.repository is None
        assert config.source.asset_pattern is None

    def test_loads_kiro_repo_config(self, config_dir):
        config = PackageConfig.from_yaml(config_dir / "kiro-repo.yaml")
        assert config.package_name == "kiro-repo"
        assert config.architecture == "all"
        assert config.source.type == "build_script"
        assert config.source.staging_prefix == "staging/kiro-repo/"

    def test_loads_depends_field(self, tmp_path):
        (tmp_path / "kiro-cli.yaml").write_text(KIRO_CLI_YAML)
        config = PackageConfig.from_yaml(tmp_path / "kiro-cli.yaml")
        assert config.depends == "kiro (>= 1.0)"
        assert config.source.type == "github_release"
        assert config.source.repository == "kiro-dev/kiro-cli"
        assert config.source.asset_pattern == "kiro-cli_*_amd64.deb"

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            PackageConfig.from_yaml(tmp_path / "nonexistent.yaml")

    def test_missing_required_field_raises(self, tmp_path):
        (tmp_path / "bad.yaml").write_text("package_name: bad\n")
        with pytest.raises(KeyError):
            PackageConfig.from_yaml(tmp_path / "bad.yaml")


class TestConfigManager:
    def test_load_all_configs(self, config_dir):
        manager = ConfigManager(str(config_dir))
        configs = manager.load_all_configs()
        assert len(configs) == 2
        names = {c.package_name for c in configs}
        assert names == {"kiro", "kiro-repo"}

    def test_load_all_configs_empty_dir(self, tmp_path):
        manager = ConfigManager(str(tmp_path))
        configs = manager.load_all_configs()
        assert configs == []

    def test_get_config_returns_correct_package(self, config_dir):
        manager = ConfigManager(str(config_dir))
        config = manager.get_config("kiro")
        assert config.package_name == "kiro"

    def test_get_config_missing_raises(self, config_dir):
        manager = ConfigManager(str(config_dir))
        with pytest.raises(FileNotFoundError):
            manager.get_config("nonexistent")

    def test_config_dir_stored_as_path(self, config_dir):
        manager = ConfigManager(str(config_dir))
        assert isinstance(manager.config_dir, Path)
