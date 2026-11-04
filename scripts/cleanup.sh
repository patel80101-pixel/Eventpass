#!/usr/bin/env bash
# Deletes everything that costs money. Run this right after the demo/viva.
set -euo pipefail
cd "$(dirname "$0")/.."
source .project.env
APP=eventpass

read -rp "This deletes the EKS cluster, load balancers and ECR images. Type YES to continue: " OK
[[ "$OK" == "YES" ]] || { echo "Cancelled."; exit 0; }

echo "==> Removing the Argo CD app and Kubernetes services (frees the load balancers)"
kubectl delete -f argocd/application.yaml --ignore-not-found || true
kubectl delete svc ${APP}-svc -n ${APP} --ignore-not-found || true
kubectl delete svc argocd-server -n argocd --ignore-not-found || true
sleep 60

echo "==> Deleting the EKS cluster (10-15 minutes)"
eksctl delete cluster -f cluster/cluster.yaml --wait

echo "==> Deleting the ECR repository and its images"
aws ecr delete-repository --repository-name ${APP} --region "$REGION" --force || true

echo "==> Deleting the GitHub Actions IAM role"
aws iam detach-role-policy --role-name github-actions-${APP} \
  --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser || true
aws iam delete-role --role-name github-actions-${APP} || true

echo
echo "✅ Cluster, images and role deleted."
echo "   Last step: terminate the EC2 instance from the AWS console (EC2 → Instances → Terminate)."
