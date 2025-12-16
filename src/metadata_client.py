"""Metadata client for fetching Kiro package information."""

import json
import logging
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import ReleaseInfo

logger = logging.getLogger(__name__)


class MetadataClient:
    """Client for fetching and parsing Kiro package metadata."""

    METADATA_URL = "https://prod.download.desktop.kiro.dev/stable/metadata-linux-x64-deb-stable.json"

    def __init__(self, timeout: int = 30, max_retries: int = 3):
        """Initialize the metadata client.

        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create a requests session with retry configuration."""
        session = requests.Session()

        # Configure retry strategy with exponential backoff
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=1,  # 1, 2, 4 seconds
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def fetch_current_metadata(self) -> dict[str, Any]:
        """Fetch current package metadata from the Kiro endpoint.

        Returns:
            Dictionary containing the parsed JSON metadata

        Raises:
            requests.RequestException: If the request fails after all retries
            json.JSONDecodeError: If the response contains invalid JSON
        """
        logger.info(f"Fetching metadata from {self.METADATA_URL}")

        try:
            response = self.session.get(self.METADATA_URL, timeout=self.timeout)
            response.raise_for_status()

            logger.info(
                f"Successfully fetched metadata (status: {response.status_code})"
            )

            # Parse JSON response
            metadata = response.json()
            logger.debug(f"Parsed metadata: {json.dumps(metadata, indent=2)}")

            return metadata

        except requests.exceptions.RequestException as e:
            logger.error(
                f"Failed to fetch metadata after {self.max_retries} retries: {e}"
            )
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse metadata JSON: {e}")
            logger.error(f"Response content: {response.text[:500]}...")
            raise

    def parse_release_info(self, metadata: dict[str, Any]) -> list[ReleaseInfo]:
        """Parse release information from metadata.

        Args:
            metadata: Raw metadata dictionary from the API

        Returns:
            List of ReleaseInfo objects

        Raises:
            KeyError: If required fields are missing from metadata
            ValueError: If metadata structure is invalid
        """
        logger.info("Parsing release information from metadata")

        try:
            # Validate required top-level fields
            required_fields = ["version", "pub_date", "url", "certificate", "signature"]
            missing_fields = [
                field for field in required_fields if field not in metadata
            ]

            if missing_fields:
                raise ValueError(
                    f"Missing required fields in metadata: {missing_fields}"
                )

            # Create ReleaseInfo from metadata
            release_info = ReleaseInfo.from_metadata(metadata)

            logger.info(
                f"Successfully parsed release info for version {release_info.version}"
            )
            logger.debug(f"Release info: {release_info}")

            return [release_info]

        except (KeyError, ValueError) as e:
            logger.error(f"Failed to parse release information: {e}")
            logger.error(f"Metadata structure: {json.dumps(metadata, indent=2)}")
            raise

    def get_current_release(self) -> ReleaseInfo:
        """Fetch and parse the current release information.

        Returns:
            ReleaseInfo object for the current release

        Raises:
            requests.RequestException: If fetching metadata fails
            json.JSONDecodeError: If JSON parsing fails
            ValueError: If metadata structure is invalid
        """
        metadata = self.fetch_current_metadata()
        releases = self.parse_release_info(metadata)

        if not releases:
            raise ValueError("No release information found in metadata")

        return releases[0]
