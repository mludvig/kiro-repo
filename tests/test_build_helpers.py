"""Unit tests for scripts/build_helpers.py."""

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

# Make scripts/ importable without installing it as a package
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from build_helpers import (
    build_dynamodb_item,
    compute_checksums,
    derive_repo_url,
    extract_terraform_outputs,
    get_infrastructure_config,
    is_valid_version,
    load_terraform_state,
    validate_required_outputs,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_state(tmp_path: Path) -> Path:
    """Write a minimal valid Terraform state file and return its path."""
    state = {
        "outputs": {
            "s3_bucket_name": {"value": "my-kiro-bucket"},
            "dynamodb_table_name": {"value": "kiro-versions-dev"},
            "lambda_function_name": {"value": "kiro-debian-repo-manager-dev"},
            "s3_bucket_website_endpoint": {
                "value": "my-kiro-bucket.s3-website-us-east-1.amazonaws.com"
            },
        }
    }
    state_file = tmp_path / "dev.tfstate"
    state_file.write_text(json.dumps(state))
    return state_file


@pytest.fixture
def sample_deb(tmp_path: Path) -> Path:
    """Create a small fake .deb file for checksum tests."""
    deb = tmp_path / "kiro-repo_1.0_all.deb"
    deb.write_bytes(b"fake deb content for testing")
    return deb


# ---------------------------------------------------------------------------
# load_terraform_state
# ---------------------------------------------------------------------------

class TestLoadTerraformState:
    def test_loads_valid_state_file(self, valid_state: Path) -> None:
        state = load_terraform_state(valid_state)
        assert "outputs" in state

    def test_raises_file_not_found_for_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            load_terraform_state(tmp_path / "nonexistent.tfstate")

    def test_raises_value_error_for_invalid_json(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.tfstate"
        bad_file.write_text("not valid json {{{")
        with pytest.raises(ValueError, match="Invalid JSON"):
            load_terraform_state(bad_file)

    def test_error_message_includes_file_path(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing.tfstate"
        with pytest.raises(FileNotFoundError) as exc_info:
            load_terraform_state(missing)
        assert "missing.tfstate" in str(exc_info.value)


# ---------------------------------------------------------------------------
# extract_terraform_outputs
# ---------------------------------------------------------------------------

class TestExtractTerraformOutputs:
    def test_extracts_string_outputs(self) -> None:
        state = {
            "outputs": {
                "s3_bucket_name": {"value": "my-bucket"},
                "lambda_function_name": {"value": "my-lambda"},
            }
        }
        outputs = extract_terraform_outputs(state)
        assert outputs["s3_bucket_name"] == "my-bucket"
        assert outputs["lambda_function_name"] == "my-lambda"

    def test_returns_empty_dict_when_no_outputs(self) -> None:
        outputs = extract_terraform_outputs({})
        assert outputs == {}

    def test_skips_entries_without_value_key(self) -> None:
        state = {
            "outputs": {
                "good": {"value": "yes"},
                "bad": {"type": "string"},
            }
        }
        outputs = extract_terraform_outputs(state)
        assert "good" in outputs
        assert "bad" not in outputs


# ---------------------------------------------------------------------------
# validate_required_outputs
# ---------------------------------------------------------------------------

class TestValidateRequiredOutputs:
    def test_passes_when_all_required_present(self) -> None:
        outputs = {
            "s3_bucket_name": "bucket",
            "dynamodb_table_name": "table",
            "lambda_function_name": "func",
        }
        # Should not raise
        validate_required_outputs(outputs)

    def test_raises_when_output_missing(self) -> None:
        outputs = {
            "s3_bucket_name": "bucket",
            "dynamodb_table_name": "table",
            # lambda_function_name missing
        }
        with pytest.raises(ValueError, match="lambda_function_name"):
            validate_required_outputs(outputs)

    def test_raises_when_output_empty_string(self) -> None:
        outputs = {
            "s3_bucket_name": "",
            "dynamodb_table_name": "table",
            "lambda_function_name": "func",
        }
        with pytest.raises(ValueError, match="s3_bucket_name"):
            validate_required_outputs(outputs)

    def test_error_lists_all_missing_outputs(self) -> None:
        with pytest.raises(ValueError) as exc_info:
            validate_required_outputs({})
        msg = str(exc_info.value)
        assert "s3_bucket_name" in msg
        assert "dynamodb_table_name" in msg
        assert "lambda_function_name" in msg


# ---------------------------------------------------------------------------
# get_infrastructure_config (integration of load + extract + validate)
# ---------------------------------------------------------------------------

class TestGetInfrastructureConfig:
    def test_returns_all_outputs_from_valid_state(self, valid_state: Path) -> None:
        config = get_infrastructure_config(valid_state)
        assert config["s3_bucket_name"] == "my-kiro-bucket"
        assert config["dynamodb_table_name"] == "kiro-versions-dev"
        assert config["lambda_function_name"] == "kiro-debian-repo-manager-dev"

    def test_raises_for_missing_state_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            get_infrastructure_config(tmp_path / "missing.tfstate")

    def test_raises_for_state_missing_required_outputs(self, tmp_path: Path) -> None:
        state_file = tmp_path / "incomplete.tfstate"
        state_file.write_text(json.dumps({"outputs": {}}))
        with pytest.raises(ValueError, match="Missing required Terraform outputs"):
            get_infrastructure_config(state_file)


# ---------------------------------------------------------------------------
# is_valid_version
# ---------------------------------------------------------------------------

class TestIsValidVersion:
    @pytest.mark.parametrize("version", ["1.0", "1.1", "2.0", "10.5", "1.2.3"])
    def test_valid_versions(self, version: str) -> None:
        assert is_valid_version(version) is True

    @pytest.mark.parametrize(
        "version",
        ["1", "1.0.0.0", "1.a", "abc", "", "1.0-beta", "1.0."],
    )
    def test_invalid_versions(self, version: str) -> None:
        assert is_valid_version(version) is False


# ---------------------------------------------------------------------------
# derive_repo_url
# ---------------------------------------------------------------------------

class TestDeriveRepoUrl:
    def test_prefers_website_endpoint(self) -> None:
        outputs = {
            "s3_bucket_name": "my-bucket",
            "s3_bucket_website_endpoint": "my-bucket.s3-website.amazonaws.com",
        }
        url = derive_repo_url(outputs)
        assert url == "http://my-bucket.s3-website.amazonaws.com"

    def test_falls_back_to_bucket_domain(self) -> None:
        outputs = {"s3_bucket_name": "my-bucket"}
        url = derive_repo_url(outputs)
        assert url == "https://my-bucket.s3.amazonaws.com"

    def test_falls_back_when_website_endpoint_empty(self) -> None:
        outputs = {
            "s3_bucket_name": "my-bucket",
            "s3_bucket_website_endpoint": "",
        }
        url = derive_repo_url(outputs)
        assert url == "https://my-bucket.s3.amazonaws.com"


# ---------------------------------------------------------------------------
# compute_checksums
# ---------------------------------------------------------------------------

class TestComputeChecksums:
    def test_returns_md5_sha1_sha256(self, sample_deb: Path) -> None:
        result = compute_checksums(sample_deb)
        assert set(result.keys()) == {"md5", "sha1", "sha256"}

    def test_checksums_are_hex_strings(self, sample_deb: Path) -> None:
        result = compute_checksums(sample_deb)
        for key, value in result.items():
            assert all(c in "0123456789abcdef" for c in value), (
                f"{key} is not a valid hex string: {value}"
            )

    def test_checksums_match_known_values(self, tmp_path: Path) -> None:
        content = b"hello world"
        f = tmp_path / "test.bin"
        f.write_bytes(content)
        result = compute_checksums(f)
        assert result["md5"] == hashlib.md5(content).hexdigest()
        assert result["sha1"] == hashlib.sha1(content).hexdigest()
        assert result["sha256"] == hashlib.sha256(content).hexdigest()

    def test_raises_for_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            compute_checksums(tmp_path / "nonexistent.deb")

    def test_different_files_produce_different_checksums(
        self, tmp_path: Path
    ) -> None:
        f1 = tmp_path / "a.deb"
        f2 = tmp_path / "b.deb"
        f1.write_bytes(b"content a")
        f2.write_bytes(b"content b")
        assert compute_checksums(f1)["sha256"] != compute_checksums(f2)["sha256"]


# ---------------------------------------------------------------------------
# build_dynamodb_item
# ---------------------------------------------------------------------------

class TestBuildDynamodbItem:
    @pytest.fixture
    def checksums(self) -> dict[str, str]:
        return {
            "md5": "d41d8cd98f00b204e9800998ecf8427e",
            "sha1": "da39a3ee5e6b4b0d3255bfef95601890afd80709",
            "sha256": (
                "e3b0c44298fc1c149afbf4c8996fb924"
                "27ae41e4649b934ca495991b7852b855"
            ),
        }

    def test_package_id_format(self, checksums: dict[str, str]) -> None:
        item = build_dynamodb_item(
            version="1.2",
            actual_filename="kiro-repo_1.2_all.deb",
            file_size=4096,
            checksums=checksums,
            staging_url="s3://bucket/staging/kiro-repo/kiro-repo_1.2_all.deb",
        )
        assert item["package_id"] == "kiro-repo#1.2"

    def test_required_fields_present(self, checksums: dict[str, str]) -> None:
        item = build_dynamodb_item(
            version="1.0",
            actual_filename="kiro-repo_1.0_all.deb",
            file_size=2048,
            checksums=checksums,
            staging_url="s3://bucket/staging/kiro-repo/kiro-repo_1.0_all.deb",
        )
        required = {
            "package_id", "package_name", "version", "architecture",
            "pub_date", "deb_url", "actual_filename", "file_size",
            "md5_hash", "sha1_hash", "sha256_hash", "section", "priority",
            "maintainer", "homepage", "description", "package_type",
            "processed_timestamp",
        }
        assert required.issubset(item.keys())

    def test_checksums_stored_correctly(self, checksums: dict[str, str]) -> None:
        item = build_dynamodb_item(
            version="1.0",
            actual_filename="kiro-repo_1.0_all.deb",
            file_size=1024,
            checksums=checksums,
            staging_url="s3://bucket/staging/kiro-repo/kiro-repo_1.0_all.deb",
        )
        assert item["md5_hash"] == checksums["md5"]
        assert item["sha1_hash"] == checksums["sha1"]
        assert item["sha256_hash"] == checksums["sha256"]

    def test_package_type_is_build_script(self, checksums: dict[str, str]) -> None:
        item = build_dynamodb_item(
            version="1.0",
            actual_filename="kiro-repo_1.0_all.deb",
            file_size=1024,
            checksums=checksums,
            staging_url="s3://bucket/staging/kiro-repo/kiro-repo_1.0_all.deb",
        )
        assert item["package_type"] == "build_script"

    def test_architecture_is_all(self, checksums: dict[str, str]) -> None:
        item = build_dynamodb_item(
            version="1.0",
            actual_filename="kiro-repo_1.0_all.deb",
            file_size=1024,
            checksums=checksums,
            staging_url="s3://bucket/staging/kiro-repo/kiro-repo_1.0_all.deb",
        )
        assert item["architecture"] == "all"

    def test_custom_pub_date_is_used(self, checksums: dict[str, str]) -> None:
        pub_date = "2025-01-15T12:00:00Z"
        item = build_dynamodb_item(
            version="1.0",
            actual_filename="kiro-repo_1.0_all.deb",
            file_size=1024,
            checksums=checksums,
            staging_url="s3://bucket/staging/kiro-repo/kiro-repo_1.0_all.deb",
            pub_date=pub_date,
        )
        assert item["pub_date"] == pub_date
        assert item["processed_timestamp"] == pub_date

    def test_default_pub_date_is_set_when_none(
        self, checksums: dict[str, str]
    ) -> None:
        item = build_dynamodb_item(
            version="1.0",
            actual_filename="kiro-repo_1.0_all.deb",
            file_size=1024,
            checksums=checksums,
            staging_url="s3://bucket/staging/kiro-repo/kiro-repo_1.0_all.deb",
        )
        assert item["pub_date"] != ""
        assert "T" in item["pub_date"]  # ISO format check
