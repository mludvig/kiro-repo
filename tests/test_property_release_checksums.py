"""Property 13: Release File Contains Packages Checksums.

For any Packages file content, the Release file should contain MD5,
SHA1, and SHA256 checksums that MATCH the actual checksums of the
Packages file content.

Validates: Requirements 10.3
"""

import hashlib
import re

from hypothesis import given, settings
from hypothesis import strategies as st

from src.models import PackageMetadata
from src.repository_builder import RepositoryBuilder

# Strategy for package names
package_names_st = st.sampled_from(["kiro", "kiro-repo", "kiro-cli"])

# Strategy for versions
version_st = st.builds(
    lambda major, minor, patch: f"{major}.{minor}.{patch}",
    major=st.integers(min_value=0, max_value=99),
    minor=st.integers(min_value=0, max_value=99),
    patch=st.integers(min_value=0, max_value=999),
)

# Strategy for PackageMetadata
package_metadata_st = st.builds(
    PackageMetadata,
    package_name=package_names_st,
    version=version_st,
    architecture=st.sampled_from(["amd64", "all"]),
    pub_date=st.dates().map(str),
    deb_url=st.builds(
        lambda name, ver: f"https://download.example.com/{name}_{ver}.deb",
        name=package_names_st,
        ver=version_st,
    ),
    actual_filename=st.builds(
        lambda name, ver, arch: f"{name}_{ver}_{arch}.deb",
        name=package_names_st,
        ver=version_st,
        arch=st.sampled_from(["amd64", "all"]),
    ),
    file_size=st.integers(min_value=1000, max_value=100000000),
    md5_hash=st.from_regex(r"[a-f0-9]{32}", fullmatch=True),
    sha1_hash=st.from_regex(r"[a-f0-9]{40}", fullmatch=True),
    sha256_hash=st.from_regex(r"[a-f0-9]{64}", fullmatch=True),
    section=st.sampled_from(["editors", "misc", "devel", "utils"]),
    priority=st.sampled_from(["optional", "required", "important"]),
    maintainer=st.just("Kiro Team <support@kiro.dev>"),
    homepage=st.just("https://kiro.dev"),
    description=st.text(
        min_size=1,
        max_size=100,
        alphabet=st.characters(
            whitelist_categories=("L", "N", "Z"),
            whitelist_characters="-_.",
        ),
    ),
    depends=st.one_of(st.none(), st.just("kiro (>= 1.0)")),
)


@given(packages=st.lists(package_metadata_st, min_size=1, max_size=5))
@settings(max_examples=50)
def test_release_checksums_match_packages_content(
    packages: list[PackageMetadata],
) -> None:
    """Checksums in Release file match actual Packages file content."""
    builder = RepositoryBuilder()
    packages_content = builder.generate_packages_file(packages)
    release_content = builder.generate_release_file(
        packages_content, packages
    )

    encoded = packages_content.encode("utf-8")
    expected_md5 = hashlib.md5(encoded).hexdigest()
    expected_sha1 = hashlib.sha1(encoded).hexdigest()
    expected_sha256 = hashlib.sha256(encoded).hexdigest()
    expected_size = len(encoded)

    # Extract checksums from Release file
    md5_match = re.search(
        r"MD5Sum:\s*\n\s*([a-f0-9]{32})\s+(\d+)", release_content
    )
    sha1_match = re.search(
        r"SHA1:\s*\n\s*([a-f0-9]{40})\s+(\d+)", release_content
    )
    sha256_match = re.search(
        r"SHA256:\s*\n\s*([a-f0-9]{64})\s+(\d+)", release_content
    )

    assert md5_match, "MD5 checksum not found in Release file"
    assert sha1_match, "SHA1 checksum not found in Release file"
    assert sha256_match, "SHA256 checksum not found in Release file"

    assert md5_match.group(1) == expected_md5, (
        f"MD5 mismatch: {md5_match.group(1)} != {expected_md5}"
    )
    assert sha1_match.group(1) == expected_sha1, (
        f"SHA1 mismatch: {sha1_match.group(1)} != {expected_sha1}"
    )
    assert sha256_match.group(1) == expected_sha256, (
        f"SHA256 mismatch: {sha256_match.group(1)} != {expected_sha256}"
    )

    # Verify sizes match too
    assert int(md5_match.group(2)) == expected_size
    assert int(sha1_match.group(2)) == expected_size
    assert int(sha256_match.group(2)) == expected_size
