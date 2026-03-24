#!/bin/bash
# Build and upload kiro-repo debian package
# Reads infrastructure resource names from Terraform state.
# Usage: ./scripts/build-kiro-repo.sh --version <version> --env <environment>

set -e

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
log_step()    { echo -e "${GREEN}✓${NC} $*"; }
log_fail()    { echo -e "${RED}✗${NC} $*" >&2; }

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
usage() {
    cat <<EOF
Usage: $0 --version <version> (--env <environment> | --repo-url <url>)

Required arguments:
  --version    Package version (e.g., 1.0, 1.1, 2.0)
  --env        Environment: dev, staging, or prod
               (reads repo URL from Terraform state)
  --repo-url   Repository base URL (skips Terraform state lookup)
               e.g. https://my-bucket.s3.amazonaws.com

Optional arguments:
  --dry-run    Build and validate the package without uploading or storing metadata
  --local      Build only; skip S3 upload, DynamoDB write, and Lambda invoke
  -h|--help    Show this help message

Examples:
  $0 --version 1.2 --env dev
  $0 --version 2.0 --env prod --dry-run
  $0 --version 1.0 --repo-url https://my-bucket.s3.amazonaws.com --local
EOF
    exit 1
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
VERSION=""
ENV=""
REPO_URL_OVERRIDE=""
DRY_RUN=false
LOCAL_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --version)   VERSION="$2";           shift 2 ;;
        --env)       ENV="$2";               shift 2 ;;
        --repo-url)  REPO_URL_OVERRIDE="$2"; shift 2 ;;
        --dry-run)   DRY_RUN=true;           shift   ;;
        --local)     LOCAL_ONLY=true;        shift   ;;
        -h|--help)   usage ;;
        *)
            log_error "Unknown argument: $1"
            usage
            ;;
    esac
done

if [[ -z "$VERSION" ]]; then
    log_error "--version is required."
    usage
fi

if [[ -z "$ENV" && -z "$REPO_URL_OVERRIDE" ]]; then
    log_error "Either --env or --repo-url is required."
    usage
fi

if [[ -n "$ENV" && ! "$ENV" =~ ^(dev|staging|prod)$ ]]; then
    log_error "Environment must be one of: dev, staging, prod"
    exit 1
fi

if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+([.][0-9]+)?$ ]]; then
    log_warn "Version '$VERSION' does not match expected format X.Y or X.Y.Z"
fi

# ---------------------------------------------------------------------------
# Resolve script and project root directories
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"
TEMPLATES_DIR="$PROJECT_ROOT/templates/kiro-repo"

# ---------------------------------------------------------------------------
# Step 1: Read Terraform state
# ---------------------------------------------------------------------------
read_terraform_state() {
    local state_file="$TERRAFORM_DIR/${ENV}.tfstate"

    log_info "Reading Terraform state from: $state_file"

    if [[ ! -f "$state_file" ]]; then
        log_fail "Terraform state file not found: $state_file"
        log_error "Please ensure Terraform has been applied for the '$ENV' environment."
        exit 1
    fi

    # Extract outputs using terraform CLI (preferred) or jq fallback
    if command -v terraform &>/dev/null; then
        S3_BUCKET=$(terraform -chdir="$TERRAFORM_DIR" output \
            -state="${ENV}.tfstate" -raw s3_bucket_name 2>/dev/null) || true
        DYNAMODB_TABLE=$(terraform -chdir="$TERRAFORM_DIR" output \
            -state="${ENV}.tfstate" -raw dynamodb_table_name 2>/dev/null) || true
        LAMBDA_FUNCTION=$(terraform -chdir="$TERRAFORM_DIR" output \
            -state="${ENV}.tfstate" -raw lambda_function_name 2>/dev/null) || true
        S3_WEBSITE=$(terraform -chdir="$TERRAFORM_DIR" output \
            -state="${ENV}.tfstate" -raw s3_bucket_website_endpoint 2>/dev/null) || true
        CF_REPO_URL=$(terraform -chdir="$TERRAFORM_DIR" output \
            -state="${ENV}.tfstate" -raw repo_url 2>/dev/null) || true
    fi

    # Fallback: parse state file directly with jq if terraform CLI failed
    if [[ -z "$S3_BUCKET" ]] && command -v jq &>/dev/null; then
        log_warn "terraform CLI output failed; falling back to jq state parsing"
        S3_BUCKET=$(jq -r \
            '.outputs.s3_bucket_name.value // empty' "$state_file" 2>/dev/null) || true
        DYNAMODB_TABLE=$(jq -r \
            '.outputs.dynamodb_table_name.value // empty' "$state_file" 2>/dev/null) || true
        LAMBDA_FUNCTION=$(jq -r \
            '.outputs.lambda_function_name.value // empty' "$state_file" 2>/dev/null) || true
        S3_WEBSITE=$(jq -r \
            '.outputs.s3_bucket_website_endpoint.value // empty' "$state_file" 2>/dev/null) || true
        CF_REPO_URL=$(jq -r \
            '.outputs.repo_url.value // empty' "$state_file" 2>/dev/null) || true
    fi

    # Validate required outputs
    local missing=()
    [[ -z "$S3_BUCKET" ]]       && missing+=("s3_bucket_name")
    [[ -z "$DYNAMODB_TABLE" ]]  && missing+=("dynamodb_table_name")
    [[ -z "$LAMBDA_FUNCTION" ]] && missing+=("lambda_function_name")

    if [[ ${#missing[@]} -gt 0 ]]; then
        log_fail "Missing required Terraform outputs: ${missing[*]}"
        log_error "Ensure the Terraform outputs are defined and the state is up to date."
        exit 1
    fi

    # Derive repo URL: prefer CloudFront, fall back to S3 website, then bucket URL
    if [[ -n "$CF_REPO_URL" ]]; then
        REPO_URL="$CF_REPO_URL"
    elif [[ -n "$S3_WEBSITE" ]]; then
        REPO_URL="http://$S3_WEBSITE"
    else
        REPO_URL="https://${S3_BUCKET}.s3.amazonaws.com"
    fi

    log_step "Terraform state loaded"
    log_info "  S3 bucket:       $S3_BUCKET"
    log_info "  DynamoDB table:  $DYNAMODB_TABLE"
    log_info "  Lambda function: $LAMBDA_FUNCTION"
    log_info "  Repository URL:  $REPO_URL"
}

# ---------------------------------------------------------------------------
# Step 2: Build the Debian package
# ---------------------------------------------------------------------------
build_package() {
    PACKAGE_NAME="kiro-repo_${VERSION}_all"
    BUILD_DIR=$(mktemp -d)
    PACKAGE_DIR="$BUILD_DIR/$PACKAGE_NAME"
    DEB_FILE="$BUILD_DIR/${PACKAGE_NAME}.deb"

    log_info "Building package in: $BUILD_DIR"

    # Validate templates exist
    if [[ ! -d "$TEMPLATES_DIR" ]]; then
        log_fail "Templates directory not found: $TEMPLATES_DIR"
        exit 1
    fi

    # Create package directory structure
    mkdir -p "$PACKAGE_DIR/DEBIAN"
    mkdir -p "$PACKAGE_DIR/etc/apt/sources.list.d"

    # Generate control file from template (replace {{VERSION}} placeholder)
    sed "s/{{VERSION}}/$VERSION/g" \
        "$TEMPLATES_DIR/DEBIAN/control" > "$PACKAGE_DIR/DEBIAN/control"
    log_step "Generated control file (version: $VERSION)"

    # Copy and make executable: postinst
    cp "$TEMPLATES_DIR/DEBIAN/postinst" "$PACKAGE_DIR/DEBIAN/postinst"
    chmod 755 "$PACKAGE_DIR/DEBIAN/postinst"
    log_step "Copied postinst script"

    # Copy and make executable: prerm
    cp "$TEMPLATES_DIR/DEBIAN/prerm" "$PACKAGE_DIR/DEBIAN/prerm"
    chmod 755 "$PACKAGE_DIR/DEBIAN/prerm"
    log_step "Copied prerm script"

    # Generate sources.list from template (replace {{REPO_URL}} placeholder)
    sed "s|{{REPO_URL}}|$REPO_URL|g" \
        "$TEMPLATES_DIR/etc/apt/sources.list.d/kiro.list" \
        > "$PACKAGE_DIR/etc/apt/sources.list.d/kiro.list"
    log_step "Generated kiro.list (repo URL: $REPO_URL)"

    # Build the .deb file
    if ! command -v dpkg-deb &>/dev/null; then
        log_fail "dpkg-deb not found. Install dpkg-dev: sudo apt-get install dpkg-dev"
        rm -rf "$BUILD_DIR"
        exit 1
    fi

    dpkg-deb --build "$PACKAGE_DIR" "$DEB_FILE"

    if [[ ! -f "$DEB_FILE" ]]; then
        log_fail "dpkg-deb did not produce: $DEB_FILE"
        rm -rf "$BUILD_DIR"
        exit 1
    fi

    log_step "Built Debian package: ${PACKAGE_NAME}.deb"

    # Compute checksums
    FILE_SIZE=$(stat -c%s "$DEB_FILE")
    MD5_HASH=$(md5sum    "$DEB_FILE" | awk '{print $1}')
    SHA1_HASH=$(sha1sum  "$DEB_FILE" | awk '{print $1}')
    SHA256_HASH=$(sha256sum "$DEB_FILE" | awk '{print $1}')

    log_info "Package checksums:"
    log_info "  Size:   $FILE_SIZE bytes"
    log_info "  MD5:    $MD5_HASH"
    log_info "  SHA1:   $SHA1_HASH"
    log_info "  SHA256: $SHA256_HASH"
}

# ---------------------------------------------------------------------------
# Step 3: Upload .deb to S3 staging area
# ---------------------------------------------------------------------------
upload_to_staging() {
    local staging_key="staging/kiro-repo/${PACKAGE_NAME}.deb"

    log_info "Uploading to S3 staging: s3://$S3_BUCKET/$staging_key"

    if ! aws s3 cp "$DEB_FILE" "s3://$S3_BUCKET/$staging_key" \
            --content-type "application/vnd.debian.binary-package"; then
        log_fail "Failed to upload .deb to S3 staging area"
        rm -rf "$BUILD_DIR"
        exit 1
    fi

    log_step "Uploaded to S3 staging: $staging_key"
}

# ---------------------------------------------------------------------------
# Step 4: Store complete PackageMetadata in DynamoDB
# ---------------------------------------------------------------------------
store_dynamodb_metadata() {
    local package_id="kiro-repo#${VERSION}"
    local pub_date
    pub_date=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    local processed_timestamp="$pub_date"
    local staging_url="s3://$S3_BUCKET/staging/kiro-repo/${PACKAGE_NAME}.deb"

    log_info "Storing metadata in DynamoDB table: $DYNAMODB_TABLE"
    log_info "  package_id: $package_id"

    local item
    item=$(cat <<EOF
{
    "package_id":           {"S": "$package_id"},
    "package_name":         {"S": "kiro-repo"},
    "version":              {"S": "$VERSION"},
    "architecture":         {"S": "all"},
    "pub_date":             {"S": "$pub_date"},
    "deb_url":              {"S": "$staging_url"},
    "actual_filename":      {"S": "${PACKAGE_NAME}.deb"},
    "file_size":            {"N": "$FILE_SIZE"},
    "md5_hash":             {"S": "$MD5_HASH"},
    "sha1_hash":            {"S": "$SHA1_HASH"},
    "sha256_hash":          {"S": "$SHA256_HASH"},
    "section":              {"S": "misc"},
    "priority":             {"S": "optional"},
    "maintainer":           {"S": "Kiro Team <support@kiro.dev>"},
    "homepage":             {"S": "https://kiro.dev"},
    "description":          {"S": "Kiro IDE Repository Configuration"},
    "package_type":         {"S": "build_script"},
    "processed_timestamp":  {"S": "$processed_timestamp"}
}
EOF
)

    if ! aws dynamodb put-item \
            --table-name "$DYNAMODB_TABLE" \
            --item "$item"; then
        log_fail "Failed to store metadata in DynamoDB"
        rm -rf "$BUILD_DIR"
        exit 1
    fi

    log_step "Stored metadata in DynamoDB (package_id: $package_id)"
}

# ---------------------------------------------------------------------------
# Step 5: Invoke Lambda with force_rebuild=true
# ---------------------------------------------------------------------------
invoke_lambda() {
    local response_file
    response_file=$(mktemp)

    log_info "Invoking Lambda function: $LAMBDA_FUNCTION"

    if ! aws lambda invoke \
            --function-name "$LAMBDA_FUNCTION" \
            --payload '{"force_rebuild": true}' \
            --cli-binary-format raw-in-base64-out \
            "$response_file" 2>/dev/null; then
        log_fail "Failed to invoke Lambda function"
        rm -f "$response_file"
        rm -rf "$BUILD_DIR"
        exit 1
    fi

    local status_code
    status_code=$(python3 -c \
        "import json,sys; d=json.load(open('$response_file')); print(d.get('statusCode',0))" \
        2>/dev/null || echo "0")

    rm -f "$response_file"

    if [[ "$status_code" != "200" ]]; then
        log_fail "Lambda function returned error status: $status_code"
        rm -rf "$BUILD_DIR"
        exit 1
    fi

    log_step "Lambda force_rebuild completed (status: $status_code)"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    echo ""
    log_info "========================================="
    log_info " Building kiro-repo package"
    log_info "  Version:     $VERSION"
    [[ -n "$ENV" ]]              && log_info "  Environment: $ENV"
    [[ -n "$REPO_URL_OVERRIDE" ]] && log_info "  Repo URL:    $REPO_URL_OVERRIDE (override)"
    [[ "$DRY_RUN"    == "true" ]] && log_info "  Mode:        DRY RUN (no upload/store)"
    [[ "$LOCAL_ONLY" == "true" ]] && log_info "  Mode:        LOCAL (build only)"
    log_info "========================================="
    echo ""

    # Step 1: Resolve repo URL
    if [[ -n "$REPO_URL_OVERRIDE" ]]; then
        REPO_URL="$REPO_URL_OVERRIDE"
        S3_BUCKET=""
        DYNAMODB_TABLE=""
        LAMBDA_FUNCTION=""
        log_step "Using provided repo URL: $REPO_URL"
    elif [[ "$DRY_RUN" == "true" ]]; then
        # In dry-run, use placeholder values if state is unavailable
        if [[ -f "$TERRAFORM_DIR/${ENV}.tfstate" ]]; then
            read_terraform_state
        else
            log_warn "Dry-run: Terraform state not found; using placeholder values"
            S3_BUCKET="<s3-bucket>"
            DYNAMODB_TABLE="<dynamodb-table>"
            LAMBDA_FUNCTION="<lambda-function>"
            REPO_URL="https://<s3-bucket>.s3.amazonaws.com"
        fi
    else
        read_terraform_state
    fi

    # Step 2: Build the package
    build_package

    if [[ "$DRY_RUN" == "true" || "$LOCAL_ONLY" == "true" ]]; then
        echo ""
        log_info "Package built at: $DEB_FILE"
        if [[ "$DRY_RUN" == "true" ]]; then
            log_info "Dry-run complete. No files were uploaded or stored."
            rm -rf "$BUILD_DIR"
        else
            log_info "Local build complete. .deb is at: $DEB_FILE"
            log_info "BUILD_DIR=$BUILD_DIR (not cleaned up)"
        fi
        exit 0
    fi

    # Step 3: Upload to S3 staging
    upload_to_staging

    # Step 4: Store metadata in DynamoDB
    store_dynamodb_metadata

    # Step 5: Invoke Lambda
    invoke_lambda

    # Cleanup
    rm -rf "$BUILD_DIR"

    echo ""
    log_info "========================================="
    log_step "Successfully built and deployed kiro-repo $VERSION"
    log_info "========================================="
    echo ""
    log_info "Users can install with:"
    log_info "  wget $REPO_URL/kiro-repo.deb"
    log_info "  sudo dpkg -i kiro-repo.deb"
    log_info "  sudo apt-get update && sudo apt-get install kiro"
    echo ""
}

main
