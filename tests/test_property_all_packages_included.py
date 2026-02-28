"""Property 9: All Packages Included in Packages File.

For any set of packages, when generating the Packages file, ALL
packages should have corresponding entries.

Validates: Requirements 4.3, 10.1
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


@given(packages=st.lists(package_metadata_st, min_size=1, max_size=8))
@settings(max_examples=50)
def test_all_packages_included_property(
    packages: list[PackageMetadata],
) -> None:
    """Every package in the input list has a corresponding entry."""
    builder = RepositoryBuilder()
    packages_content = builder.generate_packages_file(packages)

    for pkg in packages:
        assert f"Package: {pkg.package_name}" in packages_content, (
            f"Package {pkg.package_name} not found in Packages file"
        )
        assert f"Version: {pkg.version}" in packages_content, (
            f"Version {pkg.version} not found in Packages file"
        )

    # The number of "Package:" lines must equal the input count
    entry_count = packages_content.count("Package:")
    assert entry_count == len(packages), (
        f"Expected {len(packages)} entries, got {entry_count}"
    )
