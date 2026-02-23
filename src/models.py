"""Data models for the Debian Repository Manager."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class PackageMetadata:
    """Metadata for a package in the repository (multi-package support)."""

    package_name: str  # "kiro", "kiro-repo", "kiro-cli"
    version: str
    architecture: str  # "amd64", "all"
    pub_date: str

    # File information
    deb_url: str
    actual_filename: str
    file_size: int
    md5_hash: str
    sha1_hash: str
    sha256_hash: str

    # Optional fields (for kiro only)
    certificate_url: str | None = None
    signature_url: str | None = None
    notes: str | None = None

    # Metadata
    processed_timestamp: datetime | None = None

    # Package-specific metadata
    section: str = "editors"
    priority: str = "optional"
    maintainer: str = "Kiro Team <support@kiro.dev>"
    homepage: str = "https://kiro.dev"
    description: str = ""
    depends: str | None = None

    @property
    def package_id(self) -> str:
        """Compute package_id from package_name and version."""
        return f"{self.package_name}#{self.version}"

    @classmethod
    def from_metadata(cls, metadata: dict[str, Any]) -> "PackageMetadata":
        """Create PackageMetadata from flat metadata JSON.

        For existing kiro packages, sets package_name="kiro" by default.
        """
        return cls(
            package_name=metadata.get("package_name", "kiro"),
            version=metadata["version"],
            architecture=metadata.get("architecture", "amd64"),
            pub_date=metadata["pub_date"],
            deb_url=metadata["url"],
            actual_filename=metadata.get("actual_filename", ""),
            file_size=metadata.get("file_size", 0),
            md5_hash=metadata.get("md5_hash", ""),
            sha1_hash=metadata.get("sha1_hash", ""),
            sha256_hash=metadata.get("sha256_hash", ""),
            certificate_url=metadata.get("certificate"),
            signature_url=metadata.get("signature"),
            notes=metadata.get("notes"),
            section=metadata.get("section", "editors"),
            priority=metadata.get("priority", "optional"),
            maintainer=metadata.get("maintainer", "Kiro Team <support@kiro.dev>"),
            homepage=metadata.get("homepage", "https://kiro.dev"),
            description=metadata.get("description", ""),
            depends=metadata.get("depends"),
        )


@dataclass
class ReleaseInfo:
    """Information about a Kiro package release (legacy model for backward compatibility)."""

    version: str
    pub_date: str
    deb_url: str
    certificate_url: str
    signature_url: str
    notes: str
    processed_timestamp: datetime | None = None
    # File metadata (populated after download)
    actual_filename: str | None = None
    file_size: int | None = None
    md5_hash: str | None = None
    sha1_hash: str | None = None
    sha256_hash: str | None = None

    @classmethod
    def from_metadata(cls, metadata: dict[str, Any]) -> "ReleaseInfo":
        """Create ReleaseInfo from flat metadata JSON (legacy format)."""
        return cls(
            version=metadata["version"],
            pub_date=metadata["pub_date"],
            deb_url=metadata["url"],
            certificate_url=metadata["certificate"],
            signature_url=metadata["signature"],
            notes=metadata.get("notes", ""),
        )


@dataclass
class LocalReleaseFiles:
    """Local file paths for downloaded release files."""

    deb_file_path: str
    certificate_path: str
    signature_path: str
    version: str


@dataclass
class RepositoryStructure:
    """Structure of the debian repository."""

    packages_file_content: str
    release_file_content: str
    kiro_list_content: str
    deb_files: list[LocalReleaseFiles]
    base_path: str
