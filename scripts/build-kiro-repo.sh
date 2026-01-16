#!/bin/bash
# Build and upload kiro-repo debian package
# This package configures the system to use the Kiro repository

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Print usage information
usage() {
    echo "Usage: $0 --repo-url <url> --version <version> --bucket <bucket> --env <environment>"
    echo ""
    echo "Required arguments:"
    echo "  --repo-url    Repository URL (e.g., https://bucket.s3.amazonaws.com)"
    echo "  --version     Package version (e.g., 1.0, 1.1)"
    echo "  --bucket      S3 bucket name"
    echo "  --env         Environment (dev or prod)"
    echo ""
    echo "Example:"
    echo "  $0 --repo-url https://kiro-repo-prod.s3.amazonaws.com --version 1.0 --bucket kiro-repo-prod --env prod"
    exit 1
}

# Parse command line arguments
REPO_URL=""
VERSION=""
BUCKET=""
ENV=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --repo-url)
            REPO_URL="$2"
            shift 2
            ;;
        --version)
            VERSION="$2"
            shift 2
            ;;
        --bucket)
            BUCKET="$2"
            shift 2
            ;;
        --env)
            ENV="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo -e "${RED}Error: Unknown argument: $1${NC}"
            usage
            ;;
    esac
done

# Validate required arguments
if [ -z "$REPO_URL" ] || [ -z "$VERSION" ] || [ -z "$BUCKET" ] || [ -z "$ENV" ]; then
    echo -e "${RED}Error: All arguments are required${NC}"
    usage
fi

# Validate environment
if [ "$ENV" != "dev" ] && [ "$ENV" != "prod" ]; then
    echo -e "${RED}Error: Environment must be 'dev' or 'prod'${NC}"
    exit 1
fi

# Validate version format (should be numeric like 1.0, 1.1, etc.)
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+$ ]]; then
    echo -e "${YELLOW}Warning: Version format should be X.Y (e.g., 1.0)${NC}"
fi

echo -e "${GREEN}Building kiro-repo package${NC}"
echo "  Repository URL: $REPO_URL"
echo "  Version: $VERSION"
echo "  S3 Bucket: $BUCKET"
echo "  Environment: $ENV"
echo ""

# Create temporary build directory
BUILD_DIR=$(mktemp -d)
PACKAGE_NAME="kiro-repo_${VERSION}_all"
PACKAGE_DIR="$BUILD_DIR/$PACKAGE_NAME"

echo "Build directory: $BUILD_DIR"

# Create package directory structure
mkdir -p "$PACKAGE_DIR/DEBIAN"
mkdir -p "$PACKAGE_DIR/etc/apt/sources.list.d"

# Generate control file
cat > "$PACKAGE_DIR/DEBIAN/control" << EOF
Package: kiro-repo
Version: $VERSION
Section: misc
Priority: optional
Architecture: all
Maintainer: Kiro Team <support@kiro.dev>
Description: Kiro IDE Repository Configuration
 This package configures your system to use the Kiro IDE Debian repository.
 It adds the appropriate APT sources configuration to enable installation
 and updates of Kiro IDE packages.
 .
 After installation, you can install Kiro IDE with:
   sudo apt-get update
   sudo apt-get install kiro
Homepage: https://kiro.dev
EOF

echo -e "${GREEN}✓${NC} Generated control file"

# Generate kiro.list file
cat > "$PACKAGE_DIR/etc/apt/sources.list.d/kiro.list" << EOF
# Kiro IDE Debian Repository
# This repository is not GPG-signed. The [trusted=yes] option bypasses signature verification.
# The [arch=amd64] option restricts this repository to amd64 architecture only.
deb [trusted=yes arch=amd64] $REPO_URL/ stable main
EOF

echo -e "${GREEN}✓${NC} Generated kiro.list file"

# Generate postinst script
cat > "$PACKAGE_DIR/DEBIAN/postinst" << 'EOF'
#!/bin/bash
set -e

# Post-installation script for kiro-repo

case "$1" in
    configure)
        echo "Kiro IDE repository has been configured."
        echo "Run 'sudo apt-get update' to refresh package lists."
        echo "Then install Kiro IDE with 'sudo apt-get install kiro'"
        ;;
    
    abort-upgrade|abort-remove|abort-deconfigure)
        ;;
    
    *)
        echo "postinst called with unknown argument \`$1'" >&2
        exit 1
        ;;
esac

exit 0
EOF

chmod 755 "$PACKAGE_DIR/DEBIAN/postinst"

echo -e "${GREEN}✓${NC} Generated postinst script"

# Build the debian package
DEB_FILE="$BUILD_DIR/${PACKAGE_NAME}.deb"
dpkg-deb --build "$PACKAGE_DIR" "$DEB_FILE"

if [ ! -f "$DEB_FILE" ]; then
    echo -e "${RED}Error: Failed to build debian package${NC}"
    rm -rf "$BUILD_DIR"
    exit 1
fi

echo -e "${GREEN}✓${NC} Built debian package: ${PACKAGE_NAME}.deb"

# Get package file size and calculate checksums
FILE_SIZE=$(stat -c%s "$DEB_FILE")
MD5_HASH=$(md5sum "$DEB_FILE" | awk '{print $1}')
SHA1_HASH=$(sha1sum "$DEB_FILE" | awk '{print $1}')
SHA256_HASH=$(sha256sum "$DEB_FILE" | awk '{print $1}')

echo ""
echo "Package information:"
echo "  Size: $FILE_SIZE bytes"
echo "  MD5: $MD5_HASH"
echo "  SHA1: $SHA1_HASH"
echo "  SHA256: $SHA256_HASH"
echo ""

# Upload to S3
echo "Uploading to S3..."
aws s3 cp "$DEB_FILE" "s3://$BUCKET/${PACKAGE_NAME}.deb" \
    --acl public-read \
    --content-type "application/vnd.debian.binary-package"

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to upload to S3${NC}"
    rm -rf "$BUILD_DIR"
    exit 1
fi

echo -e "${GREEN}✓${NC} Uploaded to S3: s3://$BUCKET/${PACKAGE_NAME}.deb"

# Also upload with a stable name (kiro-repo.deb) for easy access
aws s3 cp "$DEB_FILE" "s3://$BUCKET/kiro-repo.deb" \
    --acl public-read \
    --content-type "application/vnd.debian.binary-package"

echo -e "${GREEN}✓${NC} Uploaded stable link: s3://$BUCKET/kiro-repo.deb"

# Update repository metadata
echo ""
echo "Updating repository metadata..."

# Download current Packages file if it exists
TEMP_PACKAGES="$BUILD_DIR/Packages"
aws s3 cp "s3://$BUCKET/dists/stable/main/binary-amd64/Packages" "$TEMP_PACKAGES" 2>/dev/null || touch "$TEMP_PACKAGES"

# Create new package entry
PACKAGE_ENTRY="Package: kiro-repo
Version: $VERSION
Architecture: all
Maintainer: Kiro Team <support@kiro.dev>
Section: misc
Priority: optional
Homepage: https://kiro.dev
Description: Kiro IDE Repository Configuration
 This package configures your system to use the Kiro IDE Debian repository.
 It adds the appropriate APT sources configuration to enable installation
 and updates of Kiro IDE packages.
Filename: pool/main/k/kiro-repo/${PACKAGE_NAME}.deb
Size: $FILE_SIZE
MD5sum: $MD5_HASH
SHA1: $SHA1_HASH
SHA256: $SHA256_HASH"

# Check if kiro-repo entry already exists in Packages file
if grep -q "^Package: kiro-repo$" "$TEMP_PACKAGES"; then
    # Remove old kiro-repo entry (everything from "Package: kiro-repo" to the next empty line or EOF)
    awk '
        BEGIN { in_kiro_repo = 0 }
        /^Package: kiro-repo$/ { in_kiro_repo = 1; next }
        /^$/ { 
            if (in_kiro_repo) { 
                in_kiro_repo = 0
                next
            }
        }
        !in_kiro_repo { print }
    ' "$TEMP_PACKAGES" > "$TEMP_PACKAGES.tmp"
    mv "$TEMP_PACKAGES.tmp" "$TEMP_PACKAGES"
    echo -e "${YELLOW}Removed old kiro-repo entry from Packages file${NC}"
fi

# Add new entry to Packages file
if [ -s "$TEMP_PACKAGES" ]; then
    # File has content, add double newline before new entry
    echo "" >> "$TEMP_PACKAGES"
    echo "" >> "$TEMP_PACKAGES"
fi
echo "$PACKAGE_ENTRY" >> "$TEMP_PACKAGES"

echo -e "${GREEN}✓${NC} Updated Packages file"

# Upload updated Packages file
aws s3 cp "$TEMP_PACKAGES" "s3://$BUCKET/dists/stable/main/binary-amd64/Packages" \
    --acl public-read \
    --content-type "text/plain"

echo -e "${GREEN}✓${NC} Uploaded Packages file to S3"

# Generate and upload Release file
PACKAGES_SIZE=$(stat -c%s "$TEMP_PACKAGES")
PACKAGES_MD5=$(md5sum "$TEMP_PACKAGES" | awk '{print $1}')
PACKAGES_SHA1=$(sha1sum "$TEMP_PACKAGES" | awk '{print $1}')
PACKAGES_SHA256=$(sha256sum "$TEMP_PACKAGES" | awk '{print $1}')

RELEASE_FILE="$BUILD_DIR/Release"
cat > "$RELEASE_FILE" << EOF
Origin: Kiro
Label: Kiro IDE Repository
Suite: stable
Codename: stable
Version: 1.0
Architectures: amd64
Components: main
Description: Kiro IDE Debian Repository - Official packages for Kiro IDE
 This repository contains official Debian packages for Kiro IDE.
Date: $(date -u "+%a, %d %b %Y %H:%M:%S UTC")
Valid-Until: $(date -u -d "+1 year" "+%a, %d %b %Y %H:%M:%S UTC")
MD5Sum:
 $PACKAGES_MD5 $PACKAGES_SIZE main/binary-amd64/Packages
SHA1:
 $PACKAGES_SHA1 $PACKAGES_SIZE main/binary-amd64/Packages
SHA256:
 $PACKAGES_SHA256 $PACKAGES_SIZE main/binary-amd64/Packages
EOF

echo -e "${GREEN}✓${NC} Generated Release file"

# Upload Release file
aws s3 cp "$RELEASE_FILE" "s3://$BUCKET/dists/stable/Release" \
    --acl public-read \
    --content-type "text/plain"

echo -e "${GREEN}✓${NC} Uploaded Release file to S3"

# Upload the actual .deb file to pool directory
aws s3 cp "$DEB_FILE" "s3://$BUCKET/pool/main/k/kiro-repo/${PACKAGE_NAME}.deb" \
    --acl public-read \
    --content-type "application/vnd.debian.binary-package"

echo -e "${GREEN}✓${NC} Uploaded package to pool directory"

# Clean up
rm -rf "$BUILD_DIR"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✓ Successfully built and uploaded kiro-repo package${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Package details:"
echo "  Name: ${PACKAGE_NAME}.deb"
echo "  Version: $VERSION"
echo "  Repository URL: $REPO_URL"
echo ""
echo "Users can install with:"
echo "  wget $REPO_URL/kiro-repo.deb"
echo "  sudo dpkg -i kiro-repo.deb"
echo "  sudo apt-get update"
echo "  sudo apt-get install kiro"
echo ""
