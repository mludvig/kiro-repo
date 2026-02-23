# Design Document

## Overview

This design extends the Debian Repository Manager to support multiple packages (kiro-ide, kiro-repo, kiro-cli) with DynamoDB as the single source of truth. The system uses versioned configuration files for build parameters and integrates all packages into a unified repository workflow. The kiro-repo package is built manually, uploaded to S3, recorded in DynamoDB, and then a force rebuild is triggered to update repository metadata.

## Architecture

The updated architecture maintains the serverless design but extends DynamoDB to track multiple packages:

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────────┐
│   CloudWatch    │───▶│  Lambda Function │───▶│   DynamoDB          │
│   Events        │    │  (Python 3.12)   │    │   Multi-Package     │
└─────────────────┘    └──────────────────┘    │   Store             │
                                │               │   - kiro-ide        │
                                │               │   - kiro-repo       │
                                ▼               │   - kiro-cli        │
                       ┌──────────────────┐    └─────────────────────┘
                       │   S3 Bucket      │
                       │   Unified Repo   │
                       └──────────────────┘
                                ▲
                       ┌──────────────────┐
                       │   Build Script   │
                       │   (Manual)       │
                       └──────────────────┘
```

**Key Changes:**
1. DynamoDB stores all packages with a `package_name` field
2. Lambda queries all packages when building repository
3. Build scripts record metadata in DynamoDB after upload
4. Force rebuild regenerates complete repository from DynamoDB

## Components and Interfaces

### 1. Enhanced Version Manager
**Purpose**: Manages version tracking for multiple packages in DynamoDB.

**Interface**:
```python
class VersionManager:
    def get_all_packages(self) -> List[PackageMetadata]
    def get_packages_by_name(self, package_name: str) -> List[PackageMetadata]
    def store_package_metadata(self, metadata: PackageMetadata) -> None
    def is_package_version_processed(self, package_name: str, version: str) -> bool
```

### 2. Configuration Manager
**Purpose**: Reads and validates build configuration from JSON/YAML files.

**Interface**:
```python
class ConfigManager:
    def load_config(self, config_path: str) -> BuildConfig
    def validate_config(self, config: BuildConfig) -> bool
    def get_environment_config(self, env: str) -> BuildConfig
```

### 3. Enhanced Repository Builder
**Purpose**: Creates repository structure including all packages.

**Interface**:
```python
class RepositoryBuilder:
    def create_repository_structure(
        self, 
        packages: List[PackageMetadata]
    ) -> RepositoryStructure
    def generate_packages_file(
        self, 
        packages: List[PackageMetadata]
    ) -> str
    def generate_package_entry(
        self, 
        package: PackageMetadata
    ) -> str
```

### 4. Terraform State Reader
**Purpose**: Reads infrastructure information from Terraform state.

**Interface**:
```python
class TerraformStateReader:
    def get_dynamodb_table_name(self, env: str) -> str
    def get_lambda_function_arn(self, env: str) -> str
    def get_s3_bucket_name(self, env: str) -> str
```

### 5. Build Script Orchestrator
**Purpose**: Coordinates the build, upload, record, and rebuild workflow.

**Workflow**:
```bash
1. Load configuration from JSON/YAML
2. Validate configuration
3. Build debian package
4. Upload to S3
5. Read DynamoDB table name from Terraform state
6. Record metadata in DynamoDB
7. Trigger force rebuild
8. Verify repository update
```

## Data Models

### PackageMetadata
```python
@dataclass
class PackageMetadata:
    package_name: str  # "kiro", "kiro-repo", "kiro-cli"
    version: str
    architecture: str  # "amd64", "all"
    pub_date: str
    
    # File information
    deb_url: str
    actual_filename: str
    file_size: int
    md5_hash: str
    sha1_hash: str
    sha256_hash: str
    
    # Optional fields (for kiro only)
    certificate_url: Optional[str] = None
    signature_url: Optional[str] = None
    notes: Optional[str] = None
    
    # Metadata
    processed_timestamp: datetime
    
    # Package-specific metadata
    section: str = "editors"  # or "misc" for kiro-repo
    priority: str = "optional"
    maintainer: str = "Kiro Team <support@kiro.dev>"
    homepage: str = "https://kiro.dev"
    description: str = ""
    depends: Optional[str] = None
```

### BuildConfig
```python
@dataclass
class BuildConfig:
    package_name: str
    version: str
    architecture: str
    
    # Repository configuration
    repo_url: str
    s3_bucket: str
    environment: str  # "dev" or "prod"
    
    # Package metadata
    section: str
    priority: str
    maintainer: str
    homepage: str
    description: str
    depends: Optional[str] = None
    
    # Build configuration
    build_dir: str
    output_dir: str
```

### DynamoDB Schema Update

**Table Name**: `kiro-package-versions-{env}`

**Primary Key**: Composite key to support multiple packages
- **Partition Key**: `package_id` (String) - Format: `{package_name}#{version}`
  - Examples: `kiro#0.7.45`, `kiro-repo#1.0`, `kiro-cli#1.2.3`
- **Sort Key**: Not needed (package_id is unique)

**Attributes**:
- `package_name`: String - "kiro", "kiro-repo", "kiro-cli"
- `version`: String - Package version
- `architecture`: String - "amd64" or "all"
- `pub_date`: String - Publication date
- `deb_url`: String - S3 URL to .deb file
- `actual_filename`: String - Actual filename
- `file_size`: Number - File size in bytes
- `md5_hash`: String - MD5 checksum
- `sha1_hash`: String - SHA1 checksum
- `sha256_hash`: String - SHA256 checksum
- `certificate_url`: String (optional) - For kiro only
- `signature_url`: String (optional) - For kiro only
- `notes`: String (optional) - Release notes
- `processed_timestamp`: String - ISO 8601 timestamp
- `section`: String - Debian section
- `priority`: String - Package priority
- `maintainer`: String - Package maintainer
- `homepage`: String - Package homepage
- `description`: String - Package description
- `depends`: String (optional) - Package dependencies

**Global Secondary Index** (optional for efficient queries):
- **Index Name**: `package-name-index`
- **Partition Key**: `package_name`
- **Sort Key**: `version`

## Directory Structure

```
kiro-repo-deb/
├── config/
│   ├── dev.json          # Development environment config
│   ├── prod.json         # Production environment config
│   └── schema.json       # JSON schema for validation
├── scripts/
│   └── build.sh          # Enhanced build script
├── templates/
│   ├── control.template  # Debian control file template
│   └── postinst.template # Post-install script template
└── README.md             # Documentation
```

### Configuration File Format (JSON)

```json
{
  "package_name": "kiro-repo",
  "version": "1.0",
  "architecture": "all",
  "repo_url": "https://kiro-repo-prod.s3.amazonaws.com",
  "s3_bucket": "kiro-repo-prod",
  "environment": "prod",
  "section": "misc",
  "priority": "optional",
  "maintainer": "Kiro Team <support@kiro.dev>",
  "homepage": "https://kiro.dev",
  "description": "Kiro IDE Repository Configuration",
  "description_long": [
    "This package configures your system to use the Kiro IDE Debian repository.",
    "It adds the appropriate APT sources configuration to enable installation",
    "and updates of Kiro IDE packages."
  ]
}
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Prework Analysis

Let me analyze each acceptance criterion for testability:

**Requirement 1: DynamoDB as Single Source of Truth**

1.1. WHEN storing package metadata, THE system SHALL include package name as a field
Thoughts: This is about data structure validation. We can generate random package metadata and verify the package_name field is present and valid.
Testable: yes - property

1.2. WHEN querying packages, THE system SHALL retrieve all packages from DynamoDB
Thoughts: This is about query completeness. We can store multiple packages and verify all are retrieved.
Testable: yes - property

1.3. WHEN building repository files, THE system SHALL use only DynamoDB data without reading from S3
Thoughts: This is about implementation behavior. We can mock S3 to ensure no reads occur during repository building.
Testable: yes - property

1.4. WHEN a force rebuild occurs, THE system SHALL generate complete repository metadata from DynamoDB alone
Thoughts: This is a round-trip property. Store packages in DynamoDB, trigger rebuild, verify all packages appear in output.
Testable: yes - property

1.5. WHEN multiple packages exist, THE system SHALL include all packages in the generated Packages file
Thoughts: This is about output completeness. Generate random packages with different names, verify all appear in Packages file.
Testable: yes - property

**Requirement 2: Configuration Files**

2.1. THE system SHALL store build configuration in JSON or YAML files
Thoughts: This is about file format. We can verify files are valid JSON/YAML.
Testable: yes - example

2.2. WHEN building a package, THE system SHALL read configuration from the appropriate file
Thoughts: This is about file I/O. We can create config files and verify they're read correctly.
Testable: yes - property

2.3. WHEN configuration includes environment-specific settings, THE system SHALL support dev and prod configurations
Thoughts: This is about configuration loading. We can verify both dev and prod configs load correctly.
Testable: yes - example

2.4. WHEN configuration changes, THE system SHALL allow version tracking through git
Thoughts: This is about git integration, not a functional requirement of our code.
Testable: no

2.5. THE configuration files SHALL include required fields
Thoughts: This is about schema validation. We can verify all required fields are present.
Testable: yes - property

**Requirement 3: Build Script DynamoDB Integration**

3.1. WHEN a kiro-repo package is built, THE build script SHALL upload the .deb file to S3
Thoughts: This is about upload behavior. We can verify upload occurs with correct parameters.
Testable: yes - property

3.2. WHEN the upload succeeds, THE build script SHALL record package metadata in DynamoDB
Thoughts: This is about conditional behavior. We can verify metadata is recorded after successful upload.
Testable: yes - property

3.3. WHEN recording metadata, THE system SHALL include all required fields
Thoughts: This is about data completeness. We can verify all fields are present in DynamoDB.
Testable: yes - property

3.4. WHEN recording metadata, THE system SHALL use the same DynamoDB table as kiro-ide packages
Thoughts: This is about table selection. We can verify the correct table is used.
Testable: yes - example

3.5. WHEN metadata is recorded, THE system SHALL include a timestamp
Thoughts: This is about field presence. We can verify timestamp exists and is valid.
Testable: yes - property

**Requirement 4: Terraform State Integration**

4.1. WHEN the build script executes, THE system SHALL read the DynamoDB table name from Terraform state
Thoughts: This is about reading Terraform state. We can verify the correct table name is extracted.
Testable: yes - property

4.2. WHEN reading Terraform state, THE system SHALL use the environment parameter to select the correct state file
Thoughts: This is about file selection. We can verify dev/prod state files are selected correctly.
Testable: yes - example

4.3. WHEN the Terraform state is unavailable, THE system SHALL provide a clear error message
Thoughts: This is error handling. We can test with missing state files.
Testable: yes - example

4.4. WHEN the table name is retrieved, THE system SHALL use it for all DynamoDB operations
Thoughts: This is about consistency. We can verify all operations use the same table name.
Testable: yes - property

4.5. WHEN multiple environments exist, THE system SHALL correctly identify the appropriate table for each
Thoughts: This is about environment isolation. We can verify dev and prod use different tables.
Testable: yes - example

**Requirement 5: Force Rebuild Triggering**

5.1. WHEN a kiro-repo package is uploaded and recorded, THE build script SHALL trigger a force rebuild
Thoughts: This is about workflow sequencing. We can verify rebuild is triggered after recording.
Testable: yes - property

5.2. WHEN triggering a force rebuild, THE system SHALL invoke the Lambda function with the force_rebuild flag
Thoughts: This is about Lambda invocation. We can verify the correct payload is sent.
Testable: yes - property

5.3. WHEN the force rebuild completes, THE system SHALL verify that repository files include the new package
Thoughts: This is about verification. We can check that the package appears in Packages file.
Testable: yes - property

5.4. WHEN the force rebuild fails, THE system SHALL provide clear error messages
Thoughts: This is error handling. We can test with failing Lambda invocations.
Testable: yes - example

5.5. WHEN triggering rebuilds, THE system SHALL use the correct Lambda function for the environment
Thoughts: This is about environment selection. We can verify dev/prod Lambda functions are used correctly.
Testable: yes - example

**Requirement 6: Lambda Multi-Package Support**

6.1. WHEN retrieving packages from DynamoDB, THE Lambda SHALL query all packages
Thoughts: This is about query completeness. We can store multiple packages and verify all are retrieved.
Testable: yes - property

6.2. WHEN generating the Packages file, THE Lambda SHALL include entries for all packages
Thoughts: This is about output completeness. We can verify all packages appear in output.
Testable: yes - property

6.3. WHEN generating package entries, THE Lambda SHALL use package-specific metadata
Thoughts: This is about metadata handling. We can verify different packages have appropriate metadata.
Testable: yes - property

6.4. WHEN building repository structure, THE Lambda SHALL organize packages by name in the pool directory
Thoughts: This is about directory structure. We can verify packages are in correct pool subdirectories.
Testable: yes - property

6.5. WHEN multiple versions of a package exist, THE Lambda SHALL include all versions
Thoughts: This is about version handling. We can store multiple versions and verify all appear.
Testable: yes - property

**Requirement 7: DynamoDB Schema**

7.1. WHEN storing package metadata, THE system SHALL include a package_name field
Thoughts: This is about field presence. We can verify the field exists and has valid values.
Testable: yes - property

7.2. WHEN storing package metadata, THE system SHALL use an appropriate schema
Thoughts: This is about schema design, not a testable behavior.
Testable: no

7.3. WHEN querying packages, THE system SHALL efficiently retrieve packages by name or all packages
Thoughts: This is about query functionality. We can verify queries return correct results.
Testable: yes - property

7.4. WHEN packages have different metadata requirements, THE system SHALL support optional fields
Thoughts: This is about schema flexibility. We can verify optional fields work correctly.
Testable: yes - property

**Requirement 8: Directory Structure**

8.1-8.5: These are about file organization, not functional requirements.
Testable: no

**Requirement 9: Configuration Validation**

9.1. WHEN the build script starts, THE system SHALL validate that required configuration fields are present
Thoughts: This is about validation. We can test with missing fields.
Testable: yes - property

9.2. WHEN configuration is invalid, THE system SHALL provide clear error messages
Thoughts: This is error handling. We can test with invalid configs.
Testable: yes - example

9.3. WHEN validating configuration, THE system SHALL check that URLs are properly formatted
Thoughts: This is about URL validation. We can test with invalid URLs.
Testable: yes - property

9.4. WHEN validating configuration, THE system SHALL verify version numbers follow semantic versioning
Thoughts: This is about version validation. We can test with invalid versions.
Testable: yes - property

9.5. WHEN validation fails, THE system SHALL exit before attempting to build
Thoughts: This is about early exit. We can verify no build occurs after validation failure.
Testable: yes - example

**Requirement 10: Logging**

10.1-10.5: These are about logging behavior, which is tested through unit tests.
Testable: yes - example (for each)

### Property Reflection

After reviewing the prework, I can consolidate some properties:

**Consolidation Opportunities:**
- Properties 1.2 and 1.5 can be combined into "query completeness across packages"
- Properties 3.3 and 3.5 can be combined into "metadata completeness"
- Properties 6.1 and 6.2 can be combined into "multi-package repository generation"
- Properties 6.4 and 6.5 can be combined into "package organization and versioning"

### Correctness Properties

**Property 1: Package Name Field Presence**
*For any* package metadata stored in DynamoDB, the package_name field should be present and contain a valid value (kiro, kiro-repo, or kiro-cli)
**Validates: Requirements 1.1, 7.1**

**Property 2: Multi-Package Query Completeness**
*For any* set of packages with different names stored in DynamoDB, querying all packages should return every package regardless of name
**Validates: Requirements 1.2, 1.5, 6.1**

**Property 3: DynamoDB-Only Repository Building**
*For any* repository build operation, the system should generate complete repository metadata using only DynamoDB data without reading from S3
**Validates: Requirements 1.3, 1.4**

**Property 4: Configuration File Validity**
*For any* configuration file, it should be valid JSON/YAML and contain all required fields with properly formatted values
**Validates: Requirements 2.1, 2.2, 2.5, 9.1, 9.3, 9.4**

**Property 5: Upload and Record Workflow**
*For any* package build, if the S3 upload succeeds, then metadata should be recorded in DynamoDB with all required fields including timestamp
**Validates: Requirements 3.1, 3.2, 3.3, 3.5**

**Property 6: Terraform State Table Resolution**
*For any* environment (dev/prod), reading the DynamoDB table name from Terraform state should return the correct table name for that environment
**Validates: Requirements 4.1, 4.2, 4.4**

**Property 7: Force Rebuild Triggering**
*For any* successful package upload and DynamoDB recording, a force rebuild should be triggered and the resulting repository should include the new package
**Validates: Requirements 5.1, 5.2, 5.3**

**Property 8: Multi-Package Repository Generation**
*For any* set of packages with different names, the generated Packages file should include entries for all packages with appropriate package-specific metadata
**Validates: Requirements 6.2, 6.3**

**Property 9: Package Organization and Versioning**
*For any* set of packages with multiple versions and names, the repository structure should organize packages by name in pool directories and include all versions
**Validates: Requirements 6.4, 6.5**

**Property 10: Optional Field Support**
*For any* package metadata, optional fields (certificate_url, signature_url, notes) should be stored when present and omitted when absent without causing errors
**Validates: Requirements 7.4**

**Property 11: Configuration Validation Early Exit**
*For any* invalid configuration, the build script should exit with an error before attempting to build or upload
**Validates: Requirements 9.5**

## Error Handling

### Configuration Errors
- Missing required fields trigger validation errors with specific field names
- Invalid JSON/YAML syntax provides parse error details
- Malformed URLs or versions provide format error messages
- Missing configuration files provide clear file path errors

### Terraform State Errors
- Missing state files provide clear error messages with expected file path
- Missing table name in state provides guidance on Terraform apply
- Invalid state file format provides parse error details

### DynamoDB Errors
- Connection failures trigger retry with exponential backoff
- Permission errors provide clear IAM policy guidance
- Duplicate package_id errors indicate version already exists
- Schema validation errors provide field-specific messages

### Lambda Invocation Errors
- Missing Lambda function provides ARN resolution guidance
- Permission errors provide IAM policy guidance
- Invocation failures provide Lambda error details
- Timeout errors suggest increasing Lambda timeout

### Build Errors
- dpkg-deb failures provide command output
- File permission errors provide chmod guidance
- Disk space errors provide cleanup suggestions

## Testing Strategy

### Unit Testing Framework
- **Framework**: pytest for Python unit testing
- **Coverage**: Configuration validation, Terraform state reading, DynamoDB operations
- **Focus**: Individual component behavior

### Property-Based Testing Framework
- **Framework**: Hypothesis for Python property-based testing
- **Configuration**: Minimum 100 iterations per property test
- **Coverage**: Multi-package scenarios, configuration validation, metadata completeness
- **Focus**: Universal properties across package types

### Integration Testing
- **Scope**: End-to-end workflow from build to force rebuild
- **Environment**: Test DynamoDB table and S3 bucket
- **Validation**: Repository metadata includes all package types

### Test Data Generation
- Package metadata generators for different package types
- Configuration file generators with valid/invalid data
- Version number generators following semantic versioning
- URL generators for S3 and repository URLs

## Migration Strategy

### One-Time Data Migration

**Challenge**: Existing kiro packages in DynamoDB use `version` as partition key, but new schema uses `package_id` as partition key.

**Solution**: One-time migration script that reads, updates, and writes back all items.

**Migration Script**:

```python
#!/usr/bin/env python3
# scripts/migrate-dynamodb-to-package-name.py
"""
One-time migration script to update DynamoDB schema from version-based keys
to package_name-based keys.

Usage:
    python scripts/migrate-dynamodb-to-package-name.py --env dev --dry-run
    python scripts/migrate-dynamodb-to-package-name.py --env prod
"""

import argparse
import boto3
import json
import sys
import subprocess
from datetime import datetime
from typing import Dict, Any, List

def get_table_name_from_terraform(env: str) -> str:
    """Read DynamoDB table name from Terraform state."""
    result = subprocess.run(
        ['terraform', 'output', f'-state=terraform/{env}.tfstate', '-raw', 'dynamodb_table_name'],
        capture_output=True,
        text=True,
        cwd='.'
    )
    
    if result.returncode != 0:
        raise Exception(f"Failed to read table name from Terraform state: {result.stderr}")
    
    return result.stdout.strip()

def migrate_item(item: Dict[str, Any]) -> tuple[Dict[str, Any], bool]:
    """Transform item from old schema to new schema.
    
    Returns:
        Tuple of (migrated_item, needs_update) where needs_update is True
        if the item was modified and needs to be written back to DynamoDB.
    """
    needs_update = False
    
    # Add package_name field (all existing items are kiro)
    if 'package_name' not in item:
        item['package_name'] = 'kiro'
        needs_update = True
    
    # Add package_id field (composite key)
    if 'package_id' not in item:
        item['package_id'] = f"kiro#{item['version']}"
        needs_update = True
    
    # Add architecture if missing (all existing kiro packages are amd64)
    if 'architecture' not in item:
        item['architecture'] = 'amd64'
        needs_update = True
    
    # Add section if missing
    if 'section' not in item:
        item['section'] = 'editors'
        needs_update = True
    
    # Add priority if missing
    if 'priority' not in item:
        item['priority'] = 'optional'
        needs_update = True
    
    # Add maintainer if missing
    if 'maintainer' not in item:
        item['maintainer'] = 'Kiro Team <support@kiro.dev>'
        needs_update = True
    
    # Add homepage if missing
    if 'homepage' not in item:
        item['homepage'] = 'https://kiro.dev'
        needs_update = True
    
    # Add description if missing
    if 'description' not in item:
        item['description'] = 'Kiro IDE - AI-powered development environment'
        needs_update = True
    
    return item, needs_update

def scan_all_items(table) -> List[Dict[str, Any]]:
    """Scan all items from DynamoDB table with pagination."""
    items = []
    response = table.scan()
    items.extend(response['Items'])
    
    while 'LastEvaluatedKey' in response:
        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        items.extend(response['Items'])
    
    return items

def migrate_table(env: str, dry_run: bool = True):
    """Migrate all items in table to new schema."""
    print(f"Starting migration for environment: {env}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print()
    
    # Get table name from Terraform
    table_name = get_table_name_from_terraform(env)
    print(f"Table name: {table_name}")
    print()
    
    # Connect to DynamoDB
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(table_name)
    
    # Scan all items
    print("Scanning existing items...")
    items = scan_all_items(table)
    print(f"Found {len(items)} items to migrate")
    print()
    
    # Migrate each item
    migrated_count = 0
    skipped_count = 0
    error_count = 0
    
    for item in items:
        try:
            old_version = item.get('version', 'unknown')
            migrated, needs_update = migrate_item(item.copy())
            
            if not needs_update:
                # Item already has all required fields, skip it
                if dry_run:
                    print(f"[DRY RUN] Would skip version {old_version} (already migrated)")
                else:
                    print(f"⊘ Skipped version {old_version} (already migrated)")
                skipped_count += 1
                continue
            
            if dry_run:
                print(f"[DRY RUN] Would migrate version {old_version}:")
                print(f"  package_name: {migrated.get('package_name')}")
                print(f"  package_id: {migrated.get('package_id')}")
                print(f"  architecture: {migrated.get('architecture')}")
            else:
                # Write migrated item back to DynamoDB
                table.put_item(Item=migrated)
                print(f"✓ Migrated version {old_version} -> {migrated['package_id']}")
            
            migrated_count += 1
            
        except Exception as e:
            print(f"✗ Error migrating item {item.get('version', 'unknown')}: {e}")
            error_count += 1
    
    print()
    print("=" * 60)
    print(f"Migration {'dry run' if dry_run else ''} completed")
    print(f"  Total items: {len(items)}")
    print(f"  Migrated: {migrated_count}")
    print(f"  Skipped (already migrated): {skipped_count}")
    print(f"  Errors: {error_count}")
    print("=" * 60)
    
    if dry_run:
        print()
        print("This was a DRY RUN. No changes were made.")
        print("Run without --dry-run to perform actual migration.")
    
    return error_count == 0

def main():
    parser = argparse.ArgumentParser(description='Migrate DynamoDB schema to package_name-based keys')
    parser.add_argument('--env', required=True, choices=['dev', 'prod'], help='Environment to migrate')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying them')
    
    args = parser.parse_args()
    
    try:
        success = migrate_table(args.env, args.dry_run)
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"Migration failed: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
```

**Migration Process**:

1. **Backup** (recommended):
   ```bash
   # Create on-demand backup before migration
   aws dynamodb create-backup \
     --table-name kiro-package-versions-dev \
     --backup-name pre-migration-backup-$(date +%Y%m%d)
   ```

2. **Dry run** to preview changes:
   ```bash
   python scripts/migrate-dynamodb-to-package-name.py --env dev --dry-run
   ```

3. **Migrate dev** environment:
   ```bash
   python scripts/migrate-dynamodb-to-package-name.py --env dev
   ```

4. **Verify** dev repository still builds:
   ```bash
   ./scripts/force-rebuild.sh dev
   ```

5. **Migrate prod** environment:
   ```bash
   python scripts/migrate-dynamodb-to-package-name.py --env prod
   ./scripts/force-rebuild.sh prod
   ```

**What the migration does**:
- Adds `package_name = "kiro"` to all existing items
- Adds `package_id = "kiro#{version}"` to all existing items
- Adds `architecture = "amd64"` if missing
- Adds Debian package metadata fields if missing (section, priority, maintainer, homepage, description)
- Preserves all existing fields (version, URLs, checksums, timestamps, etc.)
- **Idempotent**: Can be run multiple times safely - only updates items that are missing fields

**No backward compatibility code needed** - after migration, all code uses the new schema exclusively.

## Deployment Process

### Initial Setup

1. **Create kiro-repo-deb directory structure**
   ```bash
   mkdir -p kiro-repo-deb/{config,scripts,templates}
   ```

2. **Create configuration files**
   - `kiro-repo-deb/config/dev.json`
   - `kiro-repo-deb/config/prod.json`

3. **Update Terraform** (if needed for schema changes)
   ```bash
   cd terraform
   terraform plan -var-file=../config/dev.tfvars
   terraform apply -var-file=../config/dev.tfvars
   ```

4. **Run migration script** (if updating existing deployment)
   ```bash
   python scripts/migrate-dynamodb-schema.py --table kiro-package-versions-dev --dry-run
   python scripts/migrate-dynamodb-schema.py --table kiro-package-versions-dev
   ```

### Building and Uploading kiro-repo

1. **Build package**
   ```bash
   cd kiro-repo-deb
   ./scripts/build.sh --config config/prod.json
   ```

2. **Script automatically**:
   - Validates configuration
   - Builds debian package
   - Uploads to S3
   - Records in DynamoDB
   - Triggers force rebuild
   - Verifies repository update

### Verification

1. **Check DynamoDB**
   ```bash
   aws dynamodb scan --table-name kiro-package-versions-prod \
     --filter-expression "package_type = :type" \
     --expression-attribute-values '{":type":{"S":"kiro-repo"}}'
   ```

2. **Check S3**
   ```bash
   aws s3 ls s3://kiro-repo-prod/pool/main/k/kiro-repo/
   ```

3. **Check repository metadata**
   ```bash
   curl https://kiro-repo-prod.s3.amazonaws.com/dists/stable/main/binary-amd64/Packages | grep -A 20 "Package: kiro-repo"
   ```

## Future Extensibility

### Adding New Packages

To add a new package (e.g., kiro-cli):

1. **Create configuration file**
   ```json
   {
     "package_name": "kiro-cli",
     "version": "1.0.0",
     ...
   }
   ```

2. **Build and upload**
   ```bash
   ./kiro-repo-deb/scripts/build.sh --config kiro-cli-config.json
   ```

3. **No code changes needed** - the system automatically handles new packages

### Package Naming Conventions

- **Package Name**: kebab-case (kiro, kiro-repo, kiro-cli)
- **Pool Directory**: `pool/main/k/{package-name}/`
- **Architecture**: "amd64" for binaries, "all" for configuration packages
