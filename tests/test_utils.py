"""Unit tests for src/utils.py - parse_version function."""

import pytest

from src.utils import parse_version


class TestParseVersionStandard:
    def test_three_part_version(self):
        assert parse_version("1.2.3") == (1, 2, 3)

    def test_single_digit_parts(self):
        assert parse_version("0.0.1") == (0, 0, 1)

    def test_large_numbers(self):
        assert parse_version("10.20.300") == (10, 20, 300)


class TestParseVersionPartial:
    def test_two_part_version(self):
        assert parse_version("1.0") == (1, 0)

    def test_single_part_version(self):
        assert parse_version("2") == (2,)

    def test_major_minor_only(self):
        assert parse_version("3.14") == (3, 14)


class TestParseVersionNonStandard:
    def test_pre_release_suffix(self):
        assert parse_version("1.2.3-beta") == (1, 2, 3)

    def test_alpha_suffix(self):
        assert parse_version("2.0.1-alpha") == (2, 0, 1)

    def test_rc_suffix(self):
        assert parse_version("1.0-rc1") == (1, 0)

    def test_suffix_on_minor(self):
        # "1.2beta.3" splits to ["1", "2beta", "3"]
        # "2beta" -> leading digits = "2" -> 2; so result is (1, 2, 3)
        assert parse_version("1.2beta.3") == (1, 2, 3)

    def test_non_numeric_part(self):
        # Part starting with a letter has no leading digits -> fallback
        assert parse_version("1.beta.3") == (0,)


class TestParseVersionEdgeCases:
    def test_empty_string(self):
        assert parse_version("") == (0,)

    def test_none_input(self):
        assert parse_version(None) == (0,)

    def test_non_string_input(self):
        assert parse_version(123) == (0,)

    def test_only_dots(self):
        assert parse_version("...") == (0,)

    def test_leading_dot(self):
        assert parse_version(".1.2") == (0,)


class TestParseVersionComparison:
    def test_patch_increment(self):
        assert parse_version("1.2.3") < parse_version("1.2.4")

    def test_minor_increment(self):
        assert parse_version("1.9.0") < parse_version("1.10.0")

    def test_major_increment(self):
        assert parse_version("1.99.99") < parse_version("2.0.0")

    def test_equal_versions(self):
        assert parse_version("1.2.3") == parse_version("1.2.3")

    def test_older_less_than_newer(self):
        assert parse_version("0.9.9") < parse_version("1.0.0")

    def test_pre_release_comparison(self):
        # "1.2.3-beta" and "1.2.3" both parse to (1, 2, 3) — equal
        assert parse_version("1.2.3-beta") == parse_version("1.2.3")

    def test_sorting_versions(self):
        versions = ["1.10.0", "1.2.0", "2.0.0", "1.9.0"]
        sorted_versions = sorted(versions, key=parse_version)
        assert sorted_versions == ["1.2.0", "1.9.0", "1.10.0", "2.0.0"]
