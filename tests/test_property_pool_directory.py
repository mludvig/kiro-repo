"""Property 7: Pool Directory Structure.

For any package with package_name P, the pool directory path in the
Packages file should be pool/main/{first_letter_of_P}/{P}/.

Validates: Requirements 2.1, 2.5, 4.4, 11.1
"""

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
def test_pool_directory_structure_property(
    packages: list[PackageMetadata],
) -> None:
    """For any package, the Filename field follows pool/main/{P[0]}/{P}/."""
    builder = RepositoryBuilder()
    packages_content = builder.generate_packages_file(packages)

    for pkg in packages:
        expected_prefix = (
            f"pool/main/{pkg.package_name[0]}/{pkg.package_name}/"
        )
        # Find the Filename line for this package's entry
        pattern = (
            rf"Package: {re.escape(pkg.package_name)}\n"
            rf"Version: {re.escape(pkg.version)}\n"
            rf".*?Filename: ({re.escape(expected_prefix)}\S+)"
        )
        match = re.search(pattern, packages_content, re.DOTALL)
        assert match, (
            f"Expected Filename starting with {expected_prefix} "
            f"for {pkg.package_name} {pkg.version}"
        )
        filename = match.group(1)
        assert filename.startswith(expected_prefix)
        assert filename.endswith(".deb")
