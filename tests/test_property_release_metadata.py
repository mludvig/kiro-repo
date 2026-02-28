"""Property 14: Release File Metadata Completeness.

For any Release file, it should contain: Origin, Label, Suite,
Codename, Version, Architectures, Components, Description, Date,
Valid-Until, and checksum entries.

Validates: Requirements 10.4
"""

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

REQUIRED_RELEASE_FIELDS = [
    "Origin:",
    "Label:",
    "Suite:",
    "Codename:",
    "Version:",
    "Architectures:",
    "Components:",
    "Description:",
    "Date:",
    "Valid-Until:",
    "MD5Sum:",
    "SHA1:",
    "SHA256:",
]


@given(packages=st.lists(package_metadata_st, min_size=1, max_size=5))
@settings(max_examples=50)
def test_release_metadata_completeness_property(
    packages: list[PackageMetadata],
) -> None:
    """Release file contains all required metadata fields."""
    builder = RepositoryBuilder()
    packages_content = builder.generate_packages_file(packages)
    release_content = builder.generate_release_file(
        packages_content, packages
    )

    for field in REQUIRED_RELEASE_FIELDS:
        assert field in release_content, (
            f"Required field '{field}' missing from Release file"
        )

    # Verify architectures reflect the packages
    unique_archs = sorted({pkg.architecture for pkg in packages})
    expected_archs = " ".join(unique_archs)
    assert f"Architectures: {expected_archs}" in release_content, (
        f"Expected 'Architectures: {expected_archs}' in Release file"
    )
