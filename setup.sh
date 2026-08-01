#!/bin/bash
# setup.sh — Instala todas las herramientas necesarias en WSL Ubuntu
# Ejecutar dentro de WSL: bash setup.sh
#
# Nota: este script usa descargas directas (curl) en vez de apt porque
# los mirrors de apt de Ubuntu 26.04 pueden estar lentos.

set -euo pipefail

echo "=== YouTube DJ Analytics — Setup de herramientas ==="

# ── Python pip ───────────────────────────────────────────
echo "[1/5] Instalando pip..."
if ! python3 -m pip --version &>/dev/null; then
  curl -LsSf https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
  python3 /tmp/get-pip.py --break-system-packages
fi
export PATH="$HOME/.local/bin:$PATH"
python3 -m pip --version

# ── uv ──────────────────────────────────────────────────
echo "[2/5] Verificando/instalando uv..."
if ! command -v uv &>/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
uv --version

# ── Terraform ───────────────────────────────────────────
echo "[3/5] Verificando/instalando Terraform..."
if ! command -v terraform &>/dev/null; then
  TERRAFORM_VERSION="1.15.8"
  curl -fsSL "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip" \
    -o /tmp/terraform.zip
  unzip -o /tmp/terraform.zip -d "$HOME/.local/bin/"
  rm /tmp/terraform.zip
fi
terraform --version

# ── gcloud CLI ──────────────────────────────────────────
echo "[4/5] Verificando/instalando gcloud CLI..."
if ! command -v gcloud &>/dev/null; then
  curl -fsSL https://sdk.cloud.google.com | bash -s -- --disable-prompts --install-dir="$HOME/.local"
fi
export PATH="$HOME/.local/google-cloud-sdk/bin:$PATH"
gcloud --version 2>&1 | head -1

# ── Docker ──────────────────────────────────────────────
echo "[5/5] Docker..."
if command -v docker &>/dev/null; then
  docker --version
else
  echo "  Docker no esta instalado en WSL."
  echo "  >>> Instala Docker Desktop for Windows desde https://www.docker.com/products/docker-desktop/"
  echo "  >>> y habilita la integracion con WSL2 en Settings > Resources > WSL Integration."
fi

# ── Dependencias del proyecto ───────────────────────────
echo ""
echo "=== Instalando dependencias del proyecto ==="
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
uv sync

echo ""
echo "=== Setup completo ==="
echo ""
echo "Herramientas instaladas:"
echo "  uv:        $(uv --version 2>/dev/null || echo 'pendiente')"
echo "  terraform: $(terraform --version 2>/dev/null | head -1 || echo 'pendiente')"
echo "  gcloud:    $(gcloud --version 2>/dev/null | head -1 || echo 'pendiente')"
echo "  docker:    $(docker --version 2>/dev/null || echo 'pendiente - instalar Docker Desktop')"
echo ""
echo "Pendiente por hacer en WSL:"
echo "  1. Cierra y reabre WSL para recargar PATH"
echo "  2. gcloud auth login"
echo "  3. gcloud config set project <PROJECT_ID>"
echo "  4. Instalar Docker Desktop for Windows con integracion WSL2"
