"""Data models for the Debian Repository Manager."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class ReleaseInfo:
    """Information about a Kiro package release."""

    version: str
    pub_date: str
    deb_url: str
    certificate_url: str
    signature_url: str
    notes: str
    processed_timestamp: datetime | None = None

    @classmethod
    def from_metadata(cls, metadata: dict[str, Any]) -> "ReleaseInfo":
        """Create ReleaseInfo from metadata JSON."""
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
    deb_files: list[LocalReleaseFiles]
    base_path: str
