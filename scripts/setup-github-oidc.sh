#!/usr/bin/env bash
# Lets GitHub Actions log in to AWS without storing any access keys (OIDC).
# Creates: the GitHub OIDC identity provider + an IAM role that only your repo can use.
set -euo pipefail
cd "$(dirname "$0")/.."
source .project.env
ROLE_NAME=github-actions-eventpass

PROVIDER_ARN="arn:aws:iam::${ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
if aws iam get-open-id-connect-provider --open-id-connect-provider-arn "$PROVIDER_ARN" >/dev/null 2>&1; then
  echo "==> GitHub OIDC provider already exists"
else
  echo "==> Creating GitHub OIDC provider"
  aws iam create-open-id-connect-provider \
    --url https://token.actions.githubusercontent.com \
    --client-id-list sts.amazonaws.com \
    --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 >/dev/null
fi

if aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
  echo "==> Role exists - updating its trust policy"
  aws iam update-assume-role-policy --role-name "$ROLE_NAME" \
    --policy-document file://iam/github-trust-policy.json
else
  echo "==> Creating IAM role $ROLE_NAME"
  aws iam create-role --role-name "$ROLE_NAME" \
    --assume-role-policy-document file://iam/github-trust-policy.json >/dev/null
fi

echo "==> Allowing the role to push images to ECR"
aws iam attach-role-policy --role-name "$ROLE_NAME" \
  --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser

ROLE_ARN=$(aws iam get-role --role-name "$ROLE_NAME" --query Role.Arn --output text)
echo
echo "✅ Done. Copy this value into GitHub → Settings → Secrets and variables → Actions"
echo "   Secret name : AWS_ROLE_ARN"
echo "   Secret value: $ROLE_ARN"
