"""Utility functions for the Debian repository manager."""


def parse_version(version: str) -> tuple[int, ...]:
    """Parse a semantic version string into a tuple of integers for comparison.

    Handles standard semantic versions as well as non-standard versions with
    pre-release suffixes (e.g., "1.2.3-beta") by stripping non-numeric suffixes
    from each part. Falls back to (0,) for completely unparseable input.

    Args:
        version: Version string to parse (e.g., "1.2.3", "1.0", "2.0.1-beta").

    Returns:
        Tuple of integers suitable for comparison (e.g., (1, 2, 3)).

    Examples:
        >>> parse_version("1.2.3")
        (1, 2, 3)
        >>> parse_version("1.0")
        (1, 0)
        >>> parse_version("2.0.1-beta")
        (2, 0, 1)
        >>> parse_version("1.0") < parse_version("1.1")
        True
    """
    if not version or not isinstance(version, str):
        return (0,)

    try:
        parts = []
        for part in version.split("."):
            # Strip non-numeric suffix (e.g., "3-beta" -> "3")
            numeric = ""
            for ch in part:
                if ch.isdigit():
                    numeric += ch
                else:
                    break
            if numeric:
                parts.append(int(numeric))
            else:
                # Part has no leading digits — fall back
                return (0,)
        if not parts:
            return (0,)
        return tuple(parts)
    except (ValueError, AttributeError):
        return (0,)
