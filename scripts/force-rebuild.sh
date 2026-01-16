#!/bin/bash
# Force rebuild the Debian repository from DynamoDB
# This script triggers a Lambda invocation with the force_rebuild flag

set -e

# Check if environment argument is provided
if [ $# -eq 0 ]; then
    echo "Usage: $0 <environment>"
    echo "  environment: dev or prod"
    exit 1
fi

ENV=$1

# Validate environment
if [ "$ENV" != "dev" ] && [ "$ENV" != "prod" ]; then
    echo "Error: Environment must be 'dev' or 'prod'"
    exit 1
fi

# Get Lambda function ARN from Terraform state
echo "Retrieving Lambda function ARN from Terraform state..."
cd terraform

# Check if terraform state exists
if [ ! -f "${ENV}.tfstate" ]; then
    echo "Error: Terraform state file '${ENV}.tfstate' not found"
    echo "Please ensure Terraform has been applied for the $ENV environment"
    exit 1
fi

# Get function ARN from terraform output
FUNCTION_ARN=$(terraform output -state="${ENV}.tfstate" -raw lambda_function_arn 2>/dev/null)

if [ -z "$FUNCTION_ARN" ]; then
    echo "Error: Could not retrieve lambda_function_arn from Terraform state"
    echo "Please ensure the Lambda function has been deployed"
    exit 1
fi

cd ..

# Extract region from ARN (format: arn:aws:lambda:REGION:account:function:name)
REGION=$(echo "$FUNCTION_ARN" | cut -d: -f4)

echo "Force rebuilding repository for environment: $ENV"
echo "Lambda function ARN: $FUNCTION_ARN"
echo "Region: $REGION"
echo ""

# Invoke Lambda with force_rebuild flag
aws lambda invoke \
    --region "$REGION" \
    --function-name "$FUNCTION_ARN" \
    --payload '{"force_rebuild": true}' \
    --cli-binary-format raw-in-base64-out \
    response.json

echo ""
echo "Response:"
cat response.json | jq .
echo ""

# Check if successful
STATUS_CODE=$(cat response.json | jq -r '.statusCode')
if [ "$STATUS_CODE" = "200" ]; then
    echo "✓ Force rebuild completed successfully"
else
    echo "✗ Force rebuild failed"
    exit 1
fi

# Clean up
rm response.json
