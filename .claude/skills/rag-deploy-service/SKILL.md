---
name: rag-deploy-service
description: Build, push y despliegue de la imagen del Cloud Run Service de Fase 2, incluida la gestión de revisiones y tráfico. Distinto de deploy-release, que despliega el Cloud Run Job del pipeline. SIEMPRE pasa por approval-gate.
---

# rag-deploy-service

## Alcance

Publicar una nueva versión del servicio conversacional de Fase 2. [[rag-terraform-root]] crea el **recurso** Cloud Run Service; este skill cubre el ciclo de imagen: build, push a Artifact Registry y despliegue de una revisión nueva.

## Por qué no es `deploy-release`

[[deploy-release]] despliega un Cloud Run **Job**: se ejecuta, termina, y una imagen mala se nota en el siguiente `execute`. Un Cloud Run **Service** atiende tráfico de usuarios de forma continua, gestiona **revisiones y reparto de tráfico**, y una imagen mala deja el sistema caído para los tres usuarios hasta que alguien haga rollback. Son procedimientos distintos con modos de falla distintos, y por eso son skills distintos.

Lo que comparten: los dos son mutaciones de recursos reales y **los dos pasan por [[approval-gate]]**.

## Flujo

1. `uv run pytest` en verde, y el set de [[rag-evaluation-suite]] ejecutado — las 15 doradas y las 10 adversariales. El PRD §13 lo pide **antes de cada release**, no después.
2. Build con `uv sync --frozen`, igual que el pipeline (mismo `pyproject.toml`, entrypoint distinto).
3. Tag con el SHA corto del commit. **Nunca `:latest`**: sin un tag exacto no hay rollback.
4. Push a Artifact Registry.
5. Presentar a [[approval-gate]]: tag, qué cambió, y si hay delta de costo (normalmente $0; si cambian CPU, memoria, concurrencia o `min-instances`, sí lo hay y se cotiza con [[cost-guardrail]]).
6. Desplegar la revisión.
7. Verificar con las tres identidades reales que IAP sigue admitiéndolas.
8. Registrar en `infra/APPROVALS.md`.

## Dockerfile

```dockerfile
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src/rag_agent/ ./src/rag_agent/
RUN uv sync --frozen --no-dev

ENV PORT=8080
CMD ["uv", "run", "uvicorn", "rag_agent.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

`CMD` con `uvicorn`, no `ENTRYPOINT` con un módulo: un Service escucha en `$PORT`, no corre hasta terminar. Y solo se copia `src/rag_agent/` — el pipeline de Fase 1 no va en esta imagen, coherente con la prohibición de imports cruzados de [[rag-fastapi-service]].

## Despliegue y flags que cuestan dinero

```bash
gcloud run deploy rag-chat-service \
  --image=us-central1-docker.pkg.dev/medallon-youtube/<repo>/rag-agent:<sha> \
  --region=us-central1 --project=medallon-youtube \
  --no-allow-unauthenticated \
  --min-instances=0 --max-instances=2 \
  --memory=1Gi --cpu=1
```

- **`--min-instances=0`** es el scale-to-zero del que depende la línea "$0.00 - $1.00" del PRD §15. Ponerlo en 1 para evitar arranques en frío convierte un costo por uso en un costo fijo 24/7 — es un cambio de presupuesto disfrazado de ajuste de latencia, y va por [[cost-guardrail]] y [[approval-gate]].
- **`--max-instances=2`** acota el peor caso. Con tres usuarios no hay razón para más, y sí para poner un techo.
- **`--no-allow-unauthenticated`** siempre, con o sin IAP.

## Revisiones y rollback

Cada despliegue crea una revisión. Por defecto el tráfico va 100% a la nueva; el rollback es dirigir el tráfico a la revisión anterior, que sigue existiendo:

```bash
gcloud run revisions list --service=rag-chat-service --region=us-central1
gcloud run services update-traffic rag-chat-service --to-revisions=<revision-anterior>=100 --region=us-central1
```

Es la razón operativa de no usar `:latest`. **El rollback también es una mutación** y pasa por [[approval-gate]] — con la salvedad razonable de que una caída en curso es contexto de urgencia: se pide la aprobación igual, pero se presenta como tal.

## Verificación posterior obligatoria

Un despliegue que responde 200 al healthcheck puede aun así estar roto para los usuarios: IAP se configura sobre el servicio, y una revisión nueva es momento de confirmar que la allowlist sigue vigente. Probar con las tres identidades del PRD §2 antes de dar el despliegue por bueno. Ver [[rag-iap-auth]].

## Invariantes

- **Siempre por [[approval-gate]]**, incluido el rollback.
- **Tag con SHA del commit, nunca `:latest`.**
- **Pruebas y set de evaluación en verde antes de desplegar.**
- **`--no-allow-unauthenticated`** en todo despliegue.
- **`--min-instances=0`** salvo aprobación explícita de costo.
- **Verificar IAP con las tres identidades** después de cada despliegue.
- **No se mezcla con [[deploy-release]]:** dos imágenes, dos recursos, dos ciclos.

## Relación con otros skills

- El recurso Service y su IAP: [[rag-terraform-root]].
- Lo que se empaqueta: [[rag-fastapi-service]].
- La puerta de calidad previa: [[rag-evaluation-suite]].
- La verificación de acceso: [[rag-iap-auth]].
- Su equivalente en Fase 1: [[deploy-release]].
