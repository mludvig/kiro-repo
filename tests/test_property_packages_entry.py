"""Property 8: Packages File Entry Completeness.

For any package, its entry in the Packages file should contain ALL
required Debian fields: Package, Version, Architecture, Maintainer,
Section, Priority, Homepage, Description, Filename, Size, MD5sum,
SHA1, SHA256.

Validates: Requirements 2.2, 2.6, 10.2
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

REQUIRED_FIELDS = [
    "Package",
    "Version",
    "Architecture",
    "Maintainer",
    "Section",
    "Priority",
    "Homepage",
    "Description",
    "Filename",
    "Size",
    "MD5sum",
    "SHA1",
    "SHA256",
]


@given(package=package_metadata_st)
@settings(max_examples=50)
def test_packages_entry_completeness_property(
    package: PackageMetadata,
) -> None:
    """Every generated entry contains all required Debian fields."""
    builder = RepositoryBuilder()
    entry = builder.generate_package_entry(package)

    for field in REQUIRED_FIELDS:
        assert f"{field}:" in entry, (
            f"Required field '{field}' missing from entry "
            f"for {package.package_name} {package.version}"
        )
