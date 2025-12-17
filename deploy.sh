#!/bin/bash

# Deployment script for Kiro Debian Repository Manager
# This script builds the Lambda deployment package with dependencies

set -e

# Configuration
PROJECT_NAME="kiro-debian-repo-manager"
BUILD_DIR="build"
PACKAGE_DIR="$BUILD_DIR/package"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if environment is provided
if [ -z "$1" ]; then
    print_error "Usage: $0 <environment> [terraform-action]"
    print_error "Example: $0 dev plan"
    print_error "Example: $0 prod apply"
    exit 1
fi

ENVIRONMENT=$1
TERRAFORM_ACTION=${2:-plan}

print_status "Starting deployment for environment: $ENVIRONMENT"

# Validate environment
case $ENVIRONMENT in
    dev|staging|prod)
        print_status "Valid environment: $ENVIRONMENT"
        ;;
    *)
        print_error "Invalid environment: $ENVIRONMENT. Must be one of: dev, staging, prod"
        exit 1
        ;;
esac

# Check if required tools are installed
command -v python3 >/dev/null 2>&1 || { print_error "python3 is required but not installed."; exit 1; }
command -v terraform >/dev/null 2>&1 || { print_error "terraform is required but not installed."; exit 1; }

# Check if uv is available, fallback to pip
if command -v uv >/dev/null 2>&1; then
    PYTHON_INSTALLER="uv"
    print_status "Using uv for Python package management"
else
    PYTHON_INSTALLER="pip"
    print_status "Using pip for Python package management (consider installing uv for faster builds)"
fi

# Clean previous build
print_status "Cleaning previous build artifacts..."
rm -rf $BUILD_DIR
mkdir -p $PACKAGE_DIR

# Install dependencies
print_status "Installing Python dependencies..."
if [ "$PYTHON_INSTALLER" = "uv" ]; then
    # Use uv to install dependencies to the package directory
    uv pip install --target $PACKAGE_DIR -r <(uv pip compile pyproject.toml --quiet)
else
    # Use pip with virtual environment
    python3 -m venv $BUILD_DIR/venv
    source $BUILD_DIR/venv/bin/activate
    pip install -r <(python3 -c "
import tomllib
with open('pyproject.toml', 'rb') as f:
    data = tomllib.load(f)
for dep in data['project']['dependencies']:
    print(dep)
")
    pip install --target $PACKAGE_DIR boto3 requests python-dateutil
    deactivate
fi

# Copy source code
print_status "Copying source code..."
cp -r src/ $PACKAGE_DIR/
cp main.py $PACKAGE_DIR/

# Remove unnecessary files
print_status "Cleaning up package..."
find $PACKAGE_DIR -name "*.pyc" -delete
find $PACKAGE_DIR -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find $PACKAGE_DIR -name "*.egg-info" -type d -exec rm -rf {} + 2>/dev/null || true
find $PACKAGE_DIR -name "tests" -type d -exec rm -rf {} + 2>/dev/null || true

# Create deployment package
PACKAGE_FILE="$BUILD_DIR/${PROJECT_NAME}-${ENVIRONMENT}.zip"
print_status "Creating deployment package: $PACKAGE_FILE"
cd $PACKAGE_DIR
zip -r "../${PROJECT_NAME}-${ENVIRONMENT}.zip" . -q
cd - > /dev/null

PACKAGE_SIZE=$(du -h "$PACKAGE_FILE" | cut -f1)
print_status "Package created successfully (size: $PACKAGE_SIZE)"

# Check if terraform directory exists
if [ ! -d "terraform" ]; then
    print_error "Terraform directory not found. Please run this script from the project root."
    exit 1
fi

# Deploy with Terraform
print_status "Deploying infrastructure with Terraform..."
cd terraform

# Initialize Terraform if needed
if [ ! -d ".terraform" ]; then
    print_status "Initializing Terraform..."
    terraform init
fi

# Check if tfvars file exists
TFVARS_FILE="terraform.tfvars"
if [ ! -f "$TFVARS_FILE" ]; then
    print_warning "No terraform.tfvars file found. Using defaults and environment variables."
    print_warning "Consider creating $TFVARS_FILE from terraform.tfvars.example"
fi

# Set Terraform variables
export TF_VAR_env=$ENVIRONMENT
export TF_VAR_lambda_source_path="../$PACKAGE_DIR"

# Run Terraform
case $TERRAFORM_ACTION in
    plan)
        print_status "Running Terraform plan..."
        terraform plan -var-file="$TFVARS_FILE" 2>/dev/null || terraform plan
        ;;
    apply)
        print_status "Running Terraform apply..."
        terraform apply -var-file="$TFVARS_FILE" -auto-approve 2>/dev/null || terraform apply -auto-approve
        ;;
    destroy)
        print_warning "Running Terraform destroy..."
        terraform destroy -var-file="$TFVARS_FILE" -auto-approve 2>/dev/null || terraform destroy -auto-approve
        ;;
    *)
        print_error "Invalid Terraform action: $TERRAFORM_ACTION. Must be one of: plan, apply, destroy"
        exit 1
        ;;
esac

cd - > /dev/null

print_status "Deployment completed successfully!"

# Show next steps
echo
print_status "Next steps:"
echo "  1. Check the Terraform outputs for resource information"
echo "  2. Monitor CloudWatch logs: /aws/lambda/${PROJECT_NAME}-${ENVIRONMENT}"
echo "  3. Test the Lambda function manually or wait for the scheduled execution"
echo "  4. Check S3 bucket for repository files"
echo "  5. Verify DynamoDB table for version tracking"