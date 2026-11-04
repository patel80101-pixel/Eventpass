#!/usr/bin/env bash
# Fills your AWS account ID, region and GitHub details into the project files.
# Run it once, after 'aws configure' works.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Reading your AWS account ID from the AWS CLI..."
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "    AWS account ID: $ACCOUNT_ID"

read -rp "AWS region [ap-south-1]: " REGION
REGION=${REGION:-ap-south-1}
read -rp "Your GitHub username: " GH_USER
read -rp "GitHub repository name [eventpass]: " GH_REPO
GH_REPO=${GH_REPO:-eventpass}

if [[ -z "$GH_USER" ]]; then echo "GitHub username is required"; exit 1; fi

FILES="k8s/deployment.yaml argocd/application.yaml cluster/cluster.yaml iam/github-trust-policy.json .github/workflows/ci-cd.yaml"
for f in $FILES; do
  sed -i \
    -e "s|__AWS_ACCOUNT_ID__|${ACCOUNT_ID}|g" \
    -e "s|__AWS_REGION__|${REGION}|g" \
    -e "s|__GITHUB_USER__|${GH_USER}|g" \
    -e "s|__GITHUB_REPO__|${GH_REPO}|g" "$f"
done

cat > .project.env <<EOF
ACCOUNT_ID=${ACCOUNT_ID}
REGION=${REGION}
GH_USER=${GH_USER}
GH_REPO=${GH_REPO}
EOF

echo
echo "✅ Project configured:"
grep -n "image:" k8s/deployment.yaml
grep -n "repoURL" argocd/application.yaml
if grep -rq "__[A-Z_]*__" $FILES; then echo "⚠️  Some placeholders are still left:"; grep -rn "__[A-Z_]*__" $FILES; fi
