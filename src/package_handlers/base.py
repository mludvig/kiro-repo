"""Abstract base class for package type handlers."""

from abc import ABC, abstractmethod

from src.config_manager import PackageConfig
from src.models import PackageMetadata


class PackageHandler(ABC):
    """Base class for package type handlers.

    Each package type (kiro, kiro-repo, kiro-cli) implements this interface
    to define how packages are discovered, acquired, and located on disk.

    Attributes:
        config: Package configuration loaded from YAML
    """

    def __init__(self, config: PackageConfig) -> None:
        """Initialize handler with package configuration.

        Args:
            config: Package configuration defining metadata and source details
        """
        self.config = config

    @abstractmethod
    def check_new_version(self) -> str | None:
        """Check if a new version is available.

        Returns:
            Version string if a new version is available, None otherwise
        """

    @abstractmethod
    def acquire_package(self, version: str) -> PackageMetadata:
        """Acquire a package and return complete metadata.

        Downloads or locates the package for the given version and
        populates all metadata fields needed for DynamoDB storage
        and repository generation.

        Args:
            version: Version string to acquire

        Returns:
            PackageMetadata with all fields populated
        """

    @abstractmethod
    def get_package_file_path(self, metadata: PackageMetadata) -> str:
        """Get the local file path for a package.

        Args:
            metadata: Package metadata identifying the package

        Returns:
            Local filesystem path to the .deb file
        """
