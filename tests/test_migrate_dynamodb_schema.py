"""Unit tests for scripts/migrate_dynamodb_schema.py."""

import json
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# The script lives in scripts/ and does sys.path manipulation at import time,
# so we import it directly after ensuring the repo root is on sys.path.
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.migrate_dynamodb_schema import (
    DynamoDBSchemaMigration,
    KIRO_DEFAULTS,
    REQUIRED_NEW_FIELDS,
    _build_arg_parser,
    main,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

KIRO_YAML = textwrap.dedent("""\
    package_name: kiro
    description: "Kiro IDE - AI-powered development environment"
    maintainer: "Kiro Team <support@kiro.dev>"
    homepage: "https://kiro.dev"
    section: editors
    priority: optional
    architecture: amd64
    source:
      type: external_download
      metadata_endpoint: "https://download.kiro.dev/linux/metadata.json"
""")

KIRO_REPO_YAML = textwrap.dedent("""\
    package_name: kiro-repo
    description: "Kiro IDE Repository Configuration"
    maintainer: "Kiro Team <support@kiro.dev>"
    homepage: "https://kiro.dev"
    section: misc
    priority: optional
    architecture: all
    source:
      type: build_script
      staging_prefix: "staging/kiro-repo/"
""")


@pytest.fixture
def config_dir(tmp_path):
    """Temporary config directory with kiro and kiro-repo YAML files."""
    (tmp_path / "kiro.yaml").write_text(KIRO_YAML)
    (tmp_path / "kiro-repo.yaml").write_text(KIRO_REPO_YAML)
    return tmp_path


@pytest.fixture
def migration(config_dir):
    """DynamoDBSchemaMigration with mocked DynamoDB table."""
    with patch("scripts.migrate_dynamodb_schema.boto3") as mock_boto3:
        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table
        m = DynamoDBSchemaMigration(
            table_name="test-table",
            environment="dev",
            dry_run=False,
            config_dir=str(config_dir),
        )
        m.table = mock_table  # expose for assertions
        yield m


@pytest.fixture
def dry_run_migration(config_dir):
    """DynamoDBSchemaMigration in dry-run mode."""
    with patch("scripts.migrate_dynamodb_schema.boto3") as mock_boto3:
        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table
        m = DynamoDBSchemaMigration(
            table_name="test-table",
            environment="dev",
            dry_run=True,
            config_dir=str(config_dir),
        )
        m.table = mock_table
        yield m


def _old_kiro_record(version: str = "1.2.3") -> dict:
    """Build a minimal old-schema kiro record (no package_id)."""
    return {
        "version": version,
        "pub_date": "2024-01-01T00:00:00Z",
        "deb_url": f"https://example.com/kiro_{version}_amd64.deb",
        "actual_filename": f"kiro_{version}_amd64.deb",
        "file_size": 1000,
        "md5_hash": "abc",
        "sha1_hash": "def",
        "sha256_hash": "ghi",
    }


def _new_schema_record(version: str = "1.2.3", package_name: str = "kiro") -> dict:
    """Build a record that already has the new schema (package_id present)."""
    return {
        "package_id": f"{package_name}#{version}",
        "package_name": package_name,
        "version": version,
        "pub_date": "2024-01-01T00:00:00Z",
        "deb_url": f"https://example.com/{package_name}_{version}_amd64.deb",
        "actual_filename": f"{package_name}_{version}_amd64.deb",
        "file_size": 1000,
        "md5_hash": "abc",
        "sha1_hash": "def",
        "sha256_hash": "ghi",
        "architecture": "amd64",
        "section": "editors",
        "priority": "optional",
        "maintainer": "Kiro Team <support@kiro.dev>",
        "homepage": "https://kiro.dev",
        "description": "Kiro IDE - AI-powered development environment",
        "package_type": "external_download",
        "processed_timestamp": "2024-01-01T00:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# Tests: record transformation
# ---------------------------------------------------------------------------

class TestTransformRecords:
    def test_adds_package_id_to_old_record(self, migration):
        records = [_old_kiro_record("1.0.0")]
        result = migration.transform_records(records)
        assert len(result) == 1
        assert result[0]["package_id"] == "kiro#1.0.0"

    def test_defaults_package_name_to_kiro(self, migration):
        records = [_old_kiro_record("1.0.0")]
        result = migration.transform_records(records)
        assert result[0]["package_name"] == "kiro"

    def test_preserves_existing_package_name(self, migration):
        record = _old_kiro_record("2.0.0")
        record["package_name"] = "kiro-repo"
        result = migration.transform_records([record])
        assert result[0]["package_name"] == "kiro-repo"
        assert result[0]["package_id"] == "kiro-repo#2.0.0"

    def test_fills_missing_architecture(self, migration):
        records = [_old_kiro_record("1.0.0")]
        result = migration.transform_records(records)
        assert result[0]["architecture"] == "amd64"

    def test_fills_missing_section_from_config(self, migration):
        records = [_old_kiro_record("1.0.0")]
        result = migration.transform_records(records)
        assert result[0]["section"] == "editors"

    def test_fills_missing_maintainer_from_config(self, migration):
        records = [_old_kiro_record("1.0.0")]
        result = migration.transform_records(records)
        assert result[0]["maintainer"] == "Kiro Team <support@kiro.dev>"

    def test_fills_package_type(self, migration):
        records = [_old_kiro_record("1.0.0")]
        result = migration.transform_records(records)
        assert result[0]["package_type"] == "external_download"

    def test_preserves_all_existing_fields(self, migration):
        record = _old_kiro_record("1.0.0")
        record["notes"] = "some release notes"
        result = migration.transform_records([record])
        assert result[0]["notes"] == "some release notes"
        assert result[0]["deb_url"] == record["deb_url"]
        assert result[0]["sha256_hash"] == "ghi"

    def test_skips_record_without_version(self, migration):
        bad_record = {"pub_date": "2024-01-01", "deb_url": "http://x"}
        result = migration.transform_records([bad_record])
        assert result == []

    def test_all_required_fields_present_after_transform(self, migration):
        records = [_old_kiro_record("1.0.0")]
        result = migration.transform_records(records)
        assert len(result) == 1
        missing = REQUIRED_NEW_FIELDS - set(result[0].keys())
        assert missing == set(), f"Missing fields: {missing}"

    def test_transforms_multiple_records(self, migration):
        records = [_old_kiro_record(v) for v in ["1.0.0", "1.1.0", "1.2.0"]]
        result = migration.transform_records(records)
        assert len(result) == 3
        ids = {r["package_id"] for r in result}
        assert ids == {"kiro#1.0.0", "kiro#1.1.0", "kiro#1.2.0"}

    def test_kiro_repo_uses_correct_architecture(self, migration):
        record = _old_kiro_record("1.0")
        record["package_name"] = "kiro-repo"
        result = migration.transform_records([record])
        assert result[0]["architecture"] == "all"

    def test_kiro_repo_uses_correct_section(self, migration):
        record = _old_kiro_record("1.0")
        record["package_name"] = "kiro-repo"
        result = migration.transform_records([record])
        assert result[0]["section"] == "misc"

    def test_unknown_package_falls_back_to_kiro_defaults(self, migration):
        record = _old_kiro_record("0.1")
        record["package_name"] = "unknown-pkg"
        result = migration.transform_records([record])
        # Should still transform using KIRO_DEFAULTS fallback
        assert result[0]["architecture"] == KIRO_DEFAULTS["architecture"]

    def test_does_not_overwrite_existing_architecture(self, migration):
        record = _old_kiro_record("1.0.0")
        record["architecture"] = "arm64"
        result = migration.transform_records([record])
        assert result[0]["architecture"] == "arm64"

    def test_adds_processed_timestamp_if_missing(self, migration):
        records = [_old_kiro_record("1.0.0")]
        result = migration.transform_records(records)
        assert "processed_timestamp" in result[0]

    def test_preserves_existing_processed_timestamp(self, migration):
        record = _old_kiro_record("1.0.0")
        record["processed_timestamp"] = "2023-06-01T12:00:00Z"
        result = migration.transform_records([record])
        assert result[0]["processed_timestamp"] == "2023-06-01T12:00:00Z"


# ---------------------------------------------------------------------------
# Tests: backup phase
# ---------------------------------------------------------------------------

class TestBackupExistingRecords:
    def test_writes_jsonl_file(self, migration, tmp_path):
        records = [_old_kiro_record("1.0.0"), _old_kiro_record("1.1.0")]
        migration.table.scan.return_value = {"Items": records}

        backup_file = tmp_path / "backup.jsonl"
        result = migration.backup_existing_records(backup_file)

        assert backup_file.exists()
        lines = backup_file.read_text().strip().splitlines()
        assert len(lines) == 2
        assert result == records

    def test_backup_file_contains_valid_json(self, migration, tmp_path):
        records = [_old_kiro_record("1.0.0")]
        migration.table.scan.return_value = {"Items": records}

        backup_file = tmp_path / "backup.jsonl"
        migration.backup_existing_records(backup_file)

        for line in backup_file.read_text().strip().splitlines():
            parsed = json.loads(line)
            assert parsed["version"] == "1.0.0"

    def test_handles_pagination(self, migration, tmp_path):
        page1 = [_old_kiro_record("1.0.0")]
        page2 = [_old_kiro_record("1.1.0")]
        migration.table.scan.side_effect = [
            {"Items": page1, "LastEvaluatedKey": {"version": "1.0.0"}},
            {"Items": page2},
        ]

        backup_file = tmp_path / "backup.jsonl"
        result = migration.backup_existing_records(backup_file)

        assert len(result) == 2

    def test_returns_all_items(self, migration, tmp_path):
        records = [_old_kiro_record(str(i)) for i in range(5)]
        migration.table.scan.return_value = {"Items": records}

        backup_file = tmp_path / "backup.jsonl"
        result = migration.backup_existing_records(backup_file)

        assert len(result) == 5

    def test_creates_parent_directories(self, migration, tmp_path):
        migration.table.scan.return_value = {"Items": [_old_kiro_record("1.0.0")]}
        backup_file = tmp_path / "nested" / "dir" / "backup.jsonl"
        migration.backup_existing_records(backup_file)
        assert backup_file.exists()


# ---------------------------------------------------------------------------
# Tests: upload phase
# ---------------------------------------------------------------------------

class TestUploadNewRecords:
    def test_calls_batch_writer(self, migration):
        records = [_new_schema_record("1.0.0")]
        mock_batch = MagicMock()
        migration.table.batch_writer.return_value.__enter__ = MagicMock(return_value=mock_batch)
        migration.table.batch_writer.return_value.__exit__ = MagicMock(return_value=False)

        migration.upload_new_records(records)

        mock_batch.put_item.assert_called_once_with(Item=records[0])

    def test_skipped_in_dry_run(self, dry_run_migration):
        records = [_new_schema_record("1.0.0")]
        dry_run_migration.upload_new_records(records)
        dry_run_migration.table.batch_writer.assert_not_called()

    def test_uploads_multiple_records(self, migration):
        records = [_new_schema_record(str(i)) for i in range(3)]
        mock_batch = MagicMock()
        migration.table.batch_writer.return_value.__enter__ = MagicMock(return_value=mock_batch)
        migration.table.batch_writer.return_value.__exit__ = MagicMock(return_value=False)

        migration.upload_new_records(records)

        assert mock_batch.put_item.call_count == 3


# ---------------------------------------------------------------------------
# Tests: cleanup / delete phase
# ---------------------------------------------------------------------------

class TestDeleteOldRecords:
    def test_deletes_old_schema_records(self, migration):
        old_records = [_old_kiro_record("1.0.0")]  # no package_id
        mock_batch = MagicMock()
        migration.table.batch_writer.return_value.__enter__ = MagicMock(return_value=mock_batch)
        migration.table.batch_writer.return_value.__exit__ = MagicMock(return_value=False)

        migration.delete_old_records(old_records)

        mock_batch.delete_item.assert_called_once_with(Key={"version": "1.0.0"})

    def test_skips_new_schema_records(self, migration):
        new_records = [_new_schema_record("1.0.0")]  # has package_id
        mock_batch = MagicMock()
        migration.table.batch_writer.return_value.__enter__ = MagicMock(return_value=mock_batch)
        migration.table.batch_writer.return_value.__exit__ = MagicMock(return_value=False)

        migration.delete_old_records(new_records)

        mock_batch.delete_item.assert_not_called()

    def test_skipped_in_dry_run(self, dry_run_migration):
        old_records = [_old_kiro_record("1.0.0")]
        dry_run_migration.delete_old_records(old_records)
        dry_run_migration.table.batch_writer.assert_not_called()

    def test_mixed_old_and_new_records(self, migration):
        records = [
            _old_kiro_record("1.0.0"),       # old schema - should be deleted
            _new_schema_record("2.0.0"),      # new schema - should be skipped
        ]
        mock_batch = MagicMock()
        migration.table.batch_writer.return_value.__enter__ = MagicMock(return_value=mock_batch)
        migration.table.batch_writer.return_value.__exit__ = MagicMock(return_value=False)

        migration.delete_old_records(records)

        mock_batch.delete_item.assert_called_once_with(Key={"version": "1.0.0"})


# ---------------------------------------------------------------------------
# Tests: dry-run display
# ---------------------------------------------------------------------------

class TestDisplaySampleTransformations:
    def test_prints_old_and_new_records(self, migration, capsys):
        records = [_old_kiro_record("1.0.0")]
        migration.display_sample_transformations(records)
        captured = capsys.readouterr()
        assert "OLD:" in captured.out
        assert "NEW:" in captured.out
        assert "1.0.0" in captured.out

    def test_shows_at_most_3_records_by_default(self, migration, capsys):
        records = [_old_kiro_record(str(i)) for i in range(10)]
        migration.display_sample_transformations(records)
        captured = capsys.readouterr()
        # Only first 3 versions should appear
        assert "version=0" in captured.out
        assert "version=1" in captured.out
        assert "version=2" in captured.out
        assert "version=3" not in captured.out

    def test_handles_empty_records(self, migration, capsys):
        migration.display_sample_transformations([])
        captured = capsys.readouterr()
        assert "No records to display" in captured.out

    def test_custom_sample_size(self, migration, capsys):
        records = [_old_kiro_record(str(i)) for i in range(5)]
        migration.display_sample_transformations(records, sample_size=2)
        captured = capsys.readouterr()
        assert "version=0" in captured.out
        assert "version=1" in captured.out
        assert "version=2" not in captured.out


# ---------------------------------------------------------------------------
# Tests: CLI argument parsing
# ---------------------------------------------------------------------------

class TestArgParser:
    def test_requires_env(self):
        parser = _build_arg_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_accepts_dry_run_flag(self):
        parser = _build_arg_parser()
        args = parser.parse_args(["--env", "dev", "--dry-run"])
        assert args.dry_run is True

    def test_dry_run_defaults_to_false(self):
        parser = _build_arg_parser()
        args = parser.parse_args(["--env", "dev", "--backup-file", "b.jsonl"])
        assert args.dry_run is False

    def test_accepts_backup_file(self):
        parser = _build_arg_parser()
        args = parser.parse_args(["--env", "dev", "--backup-file", "backup.jsonl"])
        assert args.backup_file == Path("backup.jsonl")

    def test_accepts_all_env_choices(self):
        parser = _build_arg_parser()
        for env in ("dev", "staging", "prod"):
            args = parser.parse_args(["--env", env, "--dry-run"])
            assert args.env == env

    def test_rejects_invalid_env(self):
        parser = _build_arg_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--env", "invalid", "--dry-run"])

    def test_accepts_table_name_override(self):
        parser = _build_arg_parser()
        args = parser.parse_args(["--env", "dev", "--dry-run", "--table-name", "my-table"])
        assert args.table_name == "my-table"


# ---------------------------------------------------------------------------
# Tests: main() function
# ---------------------------------------------------------------------------

class TestMain:
    def _make_migration(self, config_dir, dry_run=False):
        """Helper to create a migration with mocked DynamoDB."""
        with patch("scripts.migrate_dynamodb_schema.boto3") as mock_boto3:
            mock_table = MagicMock()
            mock_boto3.resource.return_value.Table.return_value = mock_table
            m = DynamoDBSchemaMigration(
                table_name="test-table",
                environment="dev",
                dry_run=dry_run,
                config_dir=str(config_dir),
            )
            m.table = mock_table
            return m

    def test_requires_backup_file_for_actual_migration(self, config_dir):
        with patch("scripts.migrate_dynamodb_schema.DynamoDBSchemaMigration"):
            with pytest.raises(SystemExit) as exc_info:
                main(["--env", "dev"])
        assert exc_info.value.code != 0

    def test_dry_run_returns_zero(self, config_dir, tmp_path):
        with patch("scripts.migrate_dynamodb_schema.DynamoDBSchemaMigration") as MockMig:
            instance = MockMig.return_value
            instance.table.scan.return_value = {"Items": []}
            instance.display_sample_transformations = MagicMock()

            result = main(["--env", "dev", "--dry-run", "--config-dir", str(config_dir)])

        assert result == 0

    def test_migration_returns_zero_on_success(self, config_dir, tmp_path):
        backup_file = tmp_path / "backup.jsonl"
        records = [_old_kiro_record("1.0.0")]

        with patch("scripts.migrate_dynamodb_schema.DynamoDBSchemaMigration") as MockMig:
            instance = MockMig.return_value
            instance.backup_existing_records.return_value = records
            instance.transform_records.return_value = [_new_schema_record("1.0.0")]
            instance.upload_new_records = MagicMock()
            instance.delete_old_records = MagicMock()

            result = main([
                "--env", "dev",
                "--backup-file", str(backup_file),
                "--config-dir", str(config_dir),
            ])

        assert result == 0

    def test_migration_returns_one_on_failure(self, config_dir, tmp_path):
        backup_file = tmp_path / "backup.jsonl"

        with patch("scripts.migrate_dynamodb_schema.DynamoDBSchemaMigration") as MockMig:
            instance = MockMig.return_value
            instance.backup_existing_records.side_effect = RuntimeError("DynamoDB down")

            result = main([
                "--env", "dev",
                "--backup-file", str(backup_file),
                "--config-dir", str(config_dir),
            ])

        assert result == 1

    def test_default_table_name_uses_env(self, config_dir, tmp_path):
        backup_file = tmp_path / "backup.jsonl"

        with patch("scripts.migrate_dynamodb_schema.DynamoDBSchemaMigration") as MockMig:
            instance = MockMig.return_value
            instance.backup_existing_records.return_value = []
            instance.transform_records.return_value = []

            main([
                "--env", "staging",
                "--backup-file", str(backup_file),
                "--config-dir", str(config_dir),
            ])

            call_kwargs = MockMig.call_args
            assert call_kwargs.kwargs["table_name"] == "kiro-debian-repo-manager-versions-staging"

    def test_returns_one_when_no_records_transformed(self, config_dir, tmp_path):
        backup_file = tmp_path / "backup.jsonl"

        with patch("scripts.migrate_dynamodb_schema.DynamoDBSchemaMigration") as MockMig:
            instance = MockMig.return_value
            instance.backup_existing_records.return_value = [_old_kiro_record("1.0.0")]
            instance.transform_records.return_value = []  # all failed

            result = main([
                "--env", "dev",
                "--backup-file", str(backup_file),
                "--config-dir", str(config_dir),
            ])

        assert result == 1
