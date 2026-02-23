"""Configuration management for multi-package Debian repository."""

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class SourceConfig:
    """Configuration for package source.

    Attributes:
        type: Source type - "external_download", "build_script", or "github_release"
        metadata_endpoint: URL for external metadata endpoint (external_download only)
        staging_prefix: S3 prefix for staged packages (build_script only)
        repository: GitHub repository name (github_release only)
        asset_pattern: Glob pattern for release assets (github_release only)
    """

    type: str
    metadata_endpoint: str | None = None
    staging_prefix: str | None = None
    repository: str | None = None
    asset_pattern: str | None = None


@dataclass
class PackageConfig:
    """Configuration for a package type.

    Attributes:
        package_name: Debian package name (e.g., "kiro", "kiro-repo")
        description: Human-readable package description
        maintainer: Package maintainer in "Name <email>" format
        homepage: Package homepage URL
        section: Debian section (e.g., "editors", "misc")
        priority: Debian priority (e.g., "optional", "required")
        architecture: Target architecture (e.g., "amd64", "all")
        depends: Debian dependency string, or None
        source: Source configuration for acquiring the package
    """

    package_name: str
    description: str
    maintainer: str
    homepage: str
    section: str
    priority: str
    architecture: str
    depends: str | None
    source: SourceConfig

    @classmethod
    def from_yaml(cls, yaml_path: Path) -> "PackageConfig":
        """Load configuration from a YAML file.

        Args:
            yaml_path: Path to the YAML configuration file

        Returns:
            PackageConfig populated from the YAML file

        Raises:
            FileNotFoundError: If the YAML file does not exist
            KeyError: If required fields are missing from the YAML file
        """
        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        source_data = data["source"]
        source = SourceConfig(
            type=source_data["type"],
            metadata_endpoint=source_data.get("metadata_endpoint"),
            staging_prefix=source_data.get("staging_prefix"),
            repository=source_data.get("repository"),
            asset_pattern=source_data.get("asset_pattern"),
        )

        return cls(
            package_name=data["package_name"],
            description=data["description"],
            maintainer=data["maintainer"],
            homepage=data["homepage"],
            section=data["section"],
            priority=data["priority"],
            architecture=data["architecture"],
            depends=data.get("depends"),
            source=source,
        )


class ConfigManager:
    """Manages package configuration files.

    Loads and provides access to package configuration files stored
    in the config/packages/ directory.

    Attributes:
        config_dir: Path to the directory containing package YAML configs
    """

    def __init__(self, config_dir: str = "config/packages") -> None:
        """Initialize ConfigManager.

        Args:
            config_dir: Path to directory containing package YAML configs
        """
        self.config_dir = Path(config_dir)

    def load_all_configs(self) -> list[PackageConfig]:
        """Load all package configurations from the config directory.

        Returns:
            List of PackageConfig objects, one per YAML file found
        """
        configs = []
        for yaml_file in self.config_dir.glob("*.yaml"):
            config = PackageConfig.from_yaml(yaml_file)
            configs.append(config)
        return configs

    def get_config(self, package_name: str) -> PackageConfig:
        """Get configuration for a specific package.

        Args:
            package_name: Name of the package (e.g., "kiro", "kiro-repo")

        Returns:
            PackageConfig for the specified package

        Raises:
            FileNotFoundError: If no config file exists for the package
        """
        yaml_path = self.config_dir / f"{package_name}.yaml"
        return PackageConfig.from_yaml(yaml_path)
