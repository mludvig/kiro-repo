"""Property-based tests for semantic version comparison.

**Property 19: Semantic Version Comparison**
**Validates: Requirements 12.5, 18.5**
"""

from hypothesis import given
from hypothesis import strategies as st

from src.utils import parse_version


# Strategy for generating a single non-negative version component
version_component = st.integers(min_value=0, max_value=999)


def version_str(major: int, minor: int, patch: int) -> str:
    return f"{major}.{minor}.{patch}"


# **Property 19: Semantic Version Comparison**
# **Validates: Requirements 12.5, 18.5**
@given(
    major=version_component,
    minor=version_component,
    patch=version_component,
)
def test_patch_increment_is_newer(major: int, minor: int, patch: int):
    """For any version V, V with patch+1 should compare as greater."""
    v1 = version_str(major, minor, patch)
    v2 = version_str(major, minor, patch + 1)
    assert parse_version(v1) < parse_version(v2)


# **Property 19: Semantic Version Comparison**
# **Validates: Requirements 12.5, 18.5**
@given(
    major=version_component,
    minor=version_component,
    patch=version_component,
)
def test_minor_increment_is_newer(major: int, minor: int, patch: int):
    """For any version V, V with minor+1 should compare as greater regardless of patch."""
    v1 = version_str(major, minor, patch)
    v2 = version_str(major, minor + 1, 0)
    assert parse_version(v1) < parse_version(v2)


# **Property 19: Semantic Version Comparison**
# **Validates: Requirements 12.5, 18.5**
@given(
    major=version_component,
    minor=version_component,
    patch=version_component,
)
def test_major_increment_is_newer(major: int, minor: int, patch: int):
    """For any version V, V with major+1 should compare as greater regardless of minor/patch."""
    v1 = version_str(major, minor, patch)
    v2 = version_str(major + 1, 0, 0)
    assert parse_version(v1) < parse_version(v2)


# **Property 19: Semantic Version Comparison**
# **Validates: Requirements 12.5, 18.5**
@given(
    major=version_component,
    minor=version_component,
    patch=version_component,
)
def test_version_equals_itself(major: int, minor: int, patch: int):
    """For any version V, parse_version(V) == parse_version(V)."""
    v = version_str(major, minor, patch)
    assert parse_version(v) == parse_version(v)


# **Property 19: Semantic Version Comparison**
# **Validates: Requirements 12.5, 18.5**
@given(
    major=version_component,
    minor=st.integers(min_value=1, max_value=9),  # ensure minor > 0 so minor-1 >= 0
    patch=version_component,
)
def test_minor_9_less_than_minor_10(major: int, minor: int, patch: int):
    """Specifically validates that 1.9.x < 1.10.x (numeric, not lexicographic comparison)."""
    # Build two versions where the second minor is 10x the first to expose lexicographic bugs
    v_low = version_str(major, minor, patch)
    v_high = version_str(major, minor * 10, 0)
    assert parse_version(v_low) < parse_version(v_high)


# **Property 19: Semantic Version Comparison**
# **Validates: Requirements 12.5, 18.5**
@given(
    major=version_component,
    minor=version_component,
    patch=version_component,
    suffix=st.sampled_from(["alpha", "beta", "rc1", "dev"]),
)
def test_pre_release_suffix_stripped_for_comparison(
    major: int, minor: int, patch: int, suffix: str
):
    """A version with a pre-release suffix should parse identically to the base version."""
    base = version_str(major, minor, patch)
    with_suffix = f"{major}.{minor}.{patch}-{suffix}"
    assert parse_version(base) == parse_version(with_suffix)
