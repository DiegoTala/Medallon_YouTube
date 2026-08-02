---
name: deploy-release
description: Ciclo de build/push de la imagen Docker del contenedor de ingesta a Artifact Registry y actualización de la referencia de imagen en el Cloud Run Job. Distinto de terraform-provision, que solo crea el recurso Job/repositorio vacío. SIEMPRE pasa por approval-gate.
---

# deploy-release

## Alcance

[[terraform-provision]] crea el **recurso** Cloud Run Job y el repositorio de Artifact Registry, pero no construye ni publica la imagen del contenedor. Este skill cubre ese ciclo separado: build de la imagen Python (ingesta + validación Pydantic), push a Artifact Registry, y actualización del Cloud Run Job para que apunte a la nueva imagen (`--image`).

## Por qué es un skill separado de terraform-provision

Publicar una nueva versión del código (deploy) ocurre con mucha más frecuencia que cambios de infraestructura (provisión), y usa herramientas distintas (`docker`/`gcloud builds` en vez de `terraform`). Mezclarlos en un solo skill oscurecería cuál de los dos está mutando qué. Aun así, actualizar la imagen de un Job en producción **es una mutación de un recurso real** y por lo tanto pasa por [[approval-gate]] igual que Terraform.

## Flujo

1. Build local o vía Cloud Build, usando `uv` para resolver dependencias dentro del contenedor (ver `pyproject.toml`/`uv.lock` del proyecto).
2. Tag de la imagen con el SHA corto del commit (nunca `:latest` en producción — se necesita poder hacer rollback a una versión exacta).
3. Push a Artifact Registry.
4. Mostrar a [[approval-gate]]: qué imagen se va a desplegar (tag), qué cambió respecto a la actual (resumen del diff de código o del commit range), y confirmar que no hay cambio de costo relevante (normalmente $0 delta, salvo que cambien los límites de recursos del Job — en ese caso sí requiere [[cost-guardrail]]).
5. Tras aprobación: `gcloud run jobs update ... --image=...`.
6. Registrar en `infra/APPROVALS.md`.

## Snippet de ejemplo: Dockerfile con uv

```dockerfile
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev

ENTRYPOINT ["uv", "run", "python", "-m", "medallon_youtube.main"]
```

## Snippet de ejemplo: build, tag y push

```bash
COMMIT_SHA=$(git rev-parse --short HEAD)
IMAGE="us-central1-docker.pkg.dev/medallon-youtube/yt-pipeline/ingestion:${COMMIT_SHA}"

docker build -t "${IMAGE}" .
docker push "${IMAGE}"

echo "Imagen lista: ${IMAGE}"
# A partir de aquí: mostrar a approval-gate antes de continuar.
```

## Snippet de ejemplo: actualizar el Cloud Run Job (solo tras aprobación)

```bash
gcloud run jobs update yt-ingestion-job \
  --region=us-central1 \
  --project=medallon-youtube \
  --image="us-central1-docker.pkg.dev/medallon-youtube/yt-pipeline/ingestion:${COMMIT_SHA}"
```

## Invariantes

- **Nunca `:latest` en el Job de producción** — siempre un tag inmutable (SHA de commit) para poder hacer rollback determinista.
- **`gcloud run jobs update --image` requiere aprobación** igual que un `terraform apply`, aunque no sea un comando de Terraform — la regla de [[approval-gate]] es sobre "mutación de recurso real", no sobre la herramienta usada.
- **`uv sync --frozen`** en el build: nunca resolver dependencias "flotantes" en la imagen de producción; el lockfile manda.

## Relación con otros skills

- Depende de que [[terraform-provision]] ya haya creado el repositorio de Artifact Registry y el Cloud Run Job.
- Gateado por [[approval-gate]].
- Si cambian límites de recursos del Job como parte del release, se cotiza con [[cost-guardrail]].
