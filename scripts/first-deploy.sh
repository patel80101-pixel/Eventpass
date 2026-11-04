#!/usr/bin/env bash
# First manual deployment: create ECR repo, build + push image v1, apply Kubernetes manifests.
set -euo pipefail
cd "$(dirname "$0")/.."
source .project.env
APP=eventpass
REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

echo "==> Creating ECR repository (skipped if it exists)"
aws ecr describe-repositories --repository-names "$APP" --region "$REGION" >/dev/null 2>&1 \
  || aws ecr create-repository --repository-name "$APP" --region "$REGION" \
       --image-scanning-configuration scanOnPush=true >/dev/null

echo "==> Logging Docker in to ECR"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY"

echo "==> Building image ${APP}:v1"
docker build --build-arg APP_VERSION=v1-manual -t "${APP}:v1" .
docker tag "${APP}:v1" "${REGISTRY}/${APP}:v1"

echo "==> Pushing image to ECR"
docker push "${REGISTRY}/${APP}:v1"

echo "==> Deploying to EKS"
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/
kubectl rollout status deployment/${APP} -n ${APP} --timeout=180s
kubectl get all -n ${APP}

echo
echo "⏳ The load balancer URL can take 2-3 minutes to work. Get it with:"
echo "   kubectl get svc ${APP}-svc -n ${APP}"
