# WSL Setup — YouTube DJ Analytics

Guía de configuración del entorno de desarrollo en **WSL2 Ubuntu 26.04** para el proyecto YouTube DJ Analytics.

---

## 1. Prerequisitos del sistema

| Componente | Versión mínima |
|---|---|
| Windows | WSL2 habilitado |
| Ubuntu | 26.04 LTS |
| Python | >= 3.12 |
| git | Cualquier versión reciente |
| curl / wget | Viene preinstalado en Ubuntu |

---

## 2. Estado de herramientas

| Herramienta | Estado actual | Requerido por |
|---|---|---|
| Python 3.14 | ✅ Instalado | `pyproject.toml` (>=3.12) |
| git | ✅ Instalado | Control de versiones |
| curl / wget | ✅ Instalado | Dependencias, instaladores |
| **uv** | ❌ Faltante | Tooling Python estándar del proyecto (`pyproject.toml`, `Dockerfile`, AGENTS.md) |
| **Terraform** | ❌ Faltante | "Terraform es la única vía de mutación de infraestructura" |
| **Docker** | ❌ Faltante | Build/push de imagen del contenedor de ingesta (`deploy-release` skill) |
| **gcloud CLI** | ❌ Faltante | Diagnóstico de solo lectura de recursos GCP (`gcloud-diagnostics` skill) |
| **bq** (BigQuery CLI) | ❌ Faltante | Consultas directas a BigQuery para debugging fuera del pipeline |
| **build-essential** | ❌ Faltante | Compilación de extensiones C de dependencias Python (cryptography, etc.) |

---

## 3. Instalación paso a paso

### 3.1 Compiladores del sistema

```bash
sudo apt update && sudo apt install -y build-essential
```

### 3.2 uv (gestor de paquetes Python)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Reinicia la terminal para que `uv` esté en el PATH.

### 3.3 Terraform

```bash
sudo apt install -y gnupg software-properties-common

wget -O- https://apt.releases.hashicorp.com/gpg | \
  sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg

echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] \
  https://apt.releases.hashicorp.com $(lsb_release -cs) main" | \
  sudo tee /etc/apt/sources.list.d/hashicorp.list

sudo apt update && sudo apt install -y terraform
```

### 3.4 Docker

```bash
sudo apt install -y docker.io
sudo usermod -aG docker $USER
```

> **Importante:** Cierra y vuelve a abrir la sesión de WSL para que los permisos de grupo surtan efecto.

### 3.5 Google Cloud CLI + BigQuery

```bash
curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | \
  sudo gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg

echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] \
  https://packages.cloud.google.com/apt cloud-sdk main" | \
  sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list

sudo apt update && sudo apt install -y google-cloud-cli bq
```

---

## 4. Post-instalación

### Verificar herramientas

```bash
uv --version
terraform --version
docker --version
gcloud --version
bq --version
```

### Autenticación de Google Cloud

```bash
gcloud auth login
gcloud config set project medallon-youtube
```

---

## 5. Comandos de referencia del proyecto

```bash
# Instalar dependencias exactas del lockfile
uv sync --frozen

# Correr pruebas
uv run pytest

# Validar IaC (solo lectura)
terraform -chdir=infra fmt -check && terraform -chdir=infra validate
```
