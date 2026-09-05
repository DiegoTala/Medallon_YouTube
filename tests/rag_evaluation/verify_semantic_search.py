"""Smoke check de semantic_search contra BigQuery real.

No es un test de pytest: pega contra el proyecto y cuesta ~20 MB de escaneo
por corrida. Es la verificación de los dos bloqueantes que tuvo la herramienta
(ver infra/APPROVALS.md, 2026-09-05):

  1. roles/bigquery.connectionUser sobre vertex-ai-connection para
     rag-backend-sa — sin él, ML.GENERATE_EMBEDDING devuelve 403.
  2. maximum_bytes_billed — VECTOR_SEARCH exhaustivo lee ~20.9 MB y el tope
     de 10 MB rechazaba la consulta entera.

No hay ADC en este entorno, así que el token se pasa explícito por
GOOGLE_OAUTH_ACCESS_TOKEN.

Uso — como uno mismo (verifica el tope de bytes):
    export GOOGLE_OAUTH_ACCESS_TOKEN=$(gcloud auth print-access-token)
    .venv/bin/python tests/rag_evaluation/verify_semantic_search.py

Uso — como la SA del backend (verifica ADEMÁS el binding de la conexión):
    export GOOGLE_OAUTH_ACCESS_TOKEN=$(gcloud auth print-access-token \
        --impersonate-service-account=rag-backend-sa@medallon-youtube.iam.gserviceaccount.com)
    .venv/bin/python tests/rag_evaluation/verify_semantic_search.py

La segunda forma es la que importa para el 403: un owner pasa aunque el
binding no exista, así que correrlo como uno mismo no prueba nada del IAM.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from google.cloud import bigquery  # noqa: E402
from google.oauth2.credentials import Credentials  # noqa: E402

from rag_agent.tools.semantic_search import MAX_BYTES_BILLED, semantic_search  # noqa: E402

PROJECT = "medallon-youtube"
DATASET = "gold"
CONSULTA = "¿Qué opinan los usuarios sobre los drops de Fisher?"


def _client() -> bigquery.Client:
    token = os.environ.get("GOOGLE_OAUTH_ACCESS_TOKEN")
    if not token:
        # Sin token explícito, que intente ADC y falle con su propio mensaje.
        return bigquery.Client(project=PROJECT)
    return bigquery.Client(project=PROJECT, credentials=Credentials(token=token))


def main() -> int:
    client = _client()

    print(f"tope de bytes: {MAX_BYTES_BILLED:,} ({MAX_BYTES_BILLED / 1024**2:.0f} MB)")
    resultado = semantic_search(client, PROJECT, DATASET, CONSULTA, top_k=5)

    if resultado["status"] != "success":
        print(f"FALLO: {resultado['error']}")
        return 1

    print(f"OK: {resultado['count']} comentarios\n")
    for fila in resultado["results"]:
        print(f"  [{fila['comment_id']}] d={fila['distance']:.4f} "
              f"{fila['channel_name']} — {fila['comment_text'][:70]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
