# SETUP — YouTube DJ Analytics

Pasos manuales requeridos en Google Cloud Console y verificaciones locales para poner el proyecto en marcha.

## 1. Requisitos previos en GCP (accion del usuario)

| # | Paso | Donde | Detalle |
|:---|:---|:---|:---|
| 1 | **Crear proyecto GCP** | [Console](https://console.cloud.google.com/projectcreate) | Nombre sugerido: `medallon-youtube`. Anota el **Project ID**. |
| 2 | **Habilitar billing** | [Billing](https://console.cloud.google.com/billing) | Sin billing activo no se pueden usar APIs ni crear recursos. El presupuesto es < $15/mes. |
| 3 | **Habilitar APIs** | [API Library](https://console.cloud.google.com/apis/library) | Habilita las siguientes APIs (una por una o via `gcloud services enable`): |
|   |   |   | `youtube.googleapis.com` — YouTube Data API v3 |
|   |   |   | `run.googleapis.com` — Cloud Run API |
|   |   |   | `cloudscheduler.googleapis.com` — Cloud Scheduler |
|   |   |   | `bigquery.googleapis.com` — BigQuery |
|   |   |   | `bigqueryconnection.googleapis.com` — BigQuery Connection |
|   |   |   | `aiplatform.googleapis.com` — Vertex AI |
|   |   |   | `secretmanager.googleapis.com` — Secret Manager |
|   |   |   | `artifactregistry.googleapis.com` — Artifact Registry |
|   |   |   | `storage.googleapis.com` — Cloud Storage |
|   |   |   | `iamcredentials.googleapis.com` — IAM Credentials |
| 4 | **Crear API Key de YouTube** | [Credentials](https://console.cloud.google.com/apis/credentials) | Crear API Key > restringir a "YouTube Data API v3". Guarda la key. |
| 5 | **Crear bucket GCS para Terraform state** | [Storage](https://console.cloud.google.com/storage/browser) | Nombre: `<PROJECT_ID>-tfstate`. Habilita versionado de objetos. |
| 6 | **Autenticar gcloud localmente** | Terminal WSL | `gcloud auth login` + `gcloud config set project <PROJECT_ID>` |

### Habilitar APIs via gcloud (alternativa al paso 3 manual)

Despues del paso 6, puedes ejecutar:

```bash
gcloud services enable \
  youtube.googleapis.com \
  run.googleapis.com \
  cloudscheduler.googleapis.com \
  bigquery.googleapis.com \
  bigqueryconnection.googleapis.com \
  aiplatform.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  storage.googleapis.com \
  iamcredentials.googleapis.com
```

## 2. Instalacion de herramientas en WSL

### 2.1 Script automatico

```bash
cd ~/Medallon_YouTube
bash setup.sh
```

El script instala/verifica: `pip`, `uv`, `terraform`, `gcloud`.

### 2.2 Docker (manual)

El script no instala Docker automaticamente en WSL. La opcion recomendada es:

1. Descarga **Docker Desktop for Windows** desde https://www.docker.com/products/docker-desktop/
2. Instala y en Settings > Resources > WSL Integration, habilita tu distro Ubuntu
3. El comando `docker` estara disponible automaticamente en WSL

### 2.3 Configurar PATH en `.bashrc`

Agrega al final de `~/.bashrc` para que las herramientas esten disponibles siempre:

```bash
export PATH="$HOME/.local/bin:$HOME/.local/google-cloud-sdk/bin:$PATH"
```

Cierra y reabre WSL, o ejecuta `source ~/.bashrc`.

## 3. Verificacion

Abre una terminal WSL y ejecuta:

```bash
python3 --version     # >= 3.12
uv --version          # >= 0.4
terraform --version   # >= 1.9
gcloud --version      # cualquier version reciente
docker --version      # >= 24 (solo si Docker Desktop esta instalado)

# Verificar autenticacion GCP (requiere paso 1.6 completado)
gcloud auth list
gcloud config get-value project

# Instalar dependencias Python
cd ~/Medallon_YouTube
uv sync

# Correr tests
uv run pytest
```

## 4. Siguientes fases

| Fase | Contenido | Responsable |
|:---|:---|:---|
| **2** | Codigo de ingesta Bronze + Silver (YouTube API -> GCS -> BQ) | Agente / usuario |
| **3** | Archivos Terraform (`infra/*.tf`) + provisionamiento | Agente / usuario |
| **4** | SQL de capa Gold (sentimiento, embeddings, vector search) | Agente / usuario |
| **5** | Build Docker + deploy a Cloud Run Job | Agente / usuario |

---

*Ultima actualizacion: 2026-08-01*
