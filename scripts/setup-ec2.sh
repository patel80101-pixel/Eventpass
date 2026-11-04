#!/usr/bin/env bash
# Installs everything the project needs on a fresh Ubuntu EC2 instance:
# Docker, Git, unzip, AWS CLI v2, kubectl, eksctl
set -euo pipefail

echo "==> Updating packages"
sudo apt-get update -y
sudo apt-get install -y docker.io git unzip curl jq

echo "==> Enabling Docker for the ubuntu user"
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"

if ! command -v aws >/dev/null 2>&1; then
  echo "==> Installing AWS CLI v2"
  curl -sSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
  unzip -q -o /tmp/awscliv2.zip -d /tmp
  sudo /tmp/aws/install --update
fi

if ! command -v kubectl >/dev/null 2>&1; then
  echo "==> Installing kubectl"
  KVER=$(curl -sL https://dl.k8s.io/release/stable.txt)
  curl -sSLo /tmp/kubectl "https://dl.k8s.io/release/${KVER}/bin/linux/amd64/kubectl"
  sudo install -m 0755 /tmp/kubectl /usr/local/bin/kubectl
fi

if ! command -v eksctl >/dev/null 2>&1; then
  echo "==> Installing eksctl"
  curl -sSL "https://github.com/eksctl-io/eksctl/releases/latest/download/eksctl_Linux_amd64.tar.gz" \
    | tar xz -C /tmp
  sudo install -m 0755 /tmp/eksctl /usr/local/bin/eksctl
fi

echo
echo "==> Installed versions"
docker --version
git --version
aws --version
kubectl version --client
eksctl version
echo
echo "✅ Done. IMPORTANT: type 'exit', then SSH in again so Docker works without sudo."
