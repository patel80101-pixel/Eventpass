#!/usr/bin/env bash
# Installs Argo CD on the cluster, exposes its UI, prints the admin password, registers the app.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Installing Argo CD"
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -n argocd --server-side --force-conflicts \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

echo "==> Waiting for Argo CD to start (2-3 minutes)"
kubectl wait --for=condition=available deployment --all -n argocd --timeout=420s

echo "==> Exposing the Argo CD UI with a load balancer"
kubectl patch svc argocd-server -n argocd -p '{"spec":{"type":"LoadBalancer"}}'

echo "==> Registering the application"
kubectl apply -f argocd/application.yaml

sleep 20
URL=$(kubectl get svc argocd-server -n argocd -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
PASS=$(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d)
echo
echo "✅ Argo CD is ready"
echo "   UI       : https://${URL:-<still creating - run: kubectl get svc argocd-server -n argocd>}"
echo "   Username : admin"
echo "   Password : ${PASS}"
echo "   (Your browser will warn about the certificate - click Advanced → Proceed.)"
kubectl get applications -n argocd
