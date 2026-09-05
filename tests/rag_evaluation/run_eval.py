"""Runner de evaluación RAG contra el servicio real.

Ejecuta las 15 preguntas doradas + 10 adversariales contra el Cloud Run
Service vía JWT self-signed (IAP). Guarda evidencias en JSON/markdown.

Uso: python run_eval.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone

import requests

sys.path.insert(0, "/home/diegotala42/Medallon_YouTube")
from tests.rag_evaluation.test_cases import ADVERSARIAL_QUESTIONS, GOLDEN_QUESTIONS

SERVICE_URL = "https://rag-chat-service-7od5boefba-uc.a.run.app"
SA_EMAIL = "rag-backend-sa@medallon-youtube.iam.gserviceaccount.com"
GCLOUD = "/home/diegotala42/google-cloud-sdk/bin/gcloud"
OUT_DIR = "/home/diegotala42/Medallon_YouTube/tests/rag_evaluation/results"


def get_token(path: str = "/chat") -> str:
    payload = {
        "iss": SA_EMAIL,
        "sub": SA_EMAIL,
        "aud": f"{SERVICE_URL}{path}",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    with open("/tmp/claim.json", "w") as f:
        json.dump(payload, f)
    subprocess.run(
        [GCLOUD, "iam", "service-accounts", "sign-jwt",
         "--iam-account=" + SA_EMAIL, "/tmp/claim.json", "/tmp/rag_signed.jwt"],
        capture_output=True, text=True,
    )
    with open("/tmp/rag_signed.jwt") as f:
        return f.read().strip()


def ask(query: str, path: str = "/chat") -> dict:
    token = get_token(path)
    resp = requests.post(
        SERVICE_URL + path,
        headers={"Authorization": "Bearer " + token},
        json={"query": query},
        timeout=300,
    )
    try:
        body = resp.json()
    except Exception:
        body = {"raw": resp.text}
    return {"status_code": resp.status_code, "body": body}


def main() -> None:
    import os
    os.makedirs(OUT_DIR, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results = {"timestamp": timestamp, "golden": [], "adversarial": []}

    print(f"=== Evaluación RAG — {timestamp} ===")
    print(f"Ejecutando {len(GOLDEN_QUESTIONS)} doradas + {len(ADVERSARIAL_QUESTIONS)} adversariales...\n")

    for q in GOLDEN_QUESTIONS:
        print(f"[GOLDEN] {q['id']}: {q['query'][:60]}...")
        r = ask(q["query"])
        results["golden"].append({
            "id": q["id"], "query": q["query"],
            "status_code": r["status_code"],
            "response": r["body"].get("response", r["body"].get("raw", "")),
            "citations": r["body"].get("citations", []),
            "error": r["body"].get("error", None),
        })
        time.sleep(1)

    for q in ADVERSARIAL_QUESTIONS:
        print(f"[ADVERSARIAL] {q['id']}: {q['query'][:60]}...")
        r = ask(q["query"])
        results["adversarial"].append({
            "id": q["id"], "query": q["query"],
            "status_code": r["status_code"],
            "response": r["body"].get("response", r["body"].get("raw", "")),
            "citations": r["body"].get("citations", []),
            "error": r["body"].get("error", None),
        })
        time.sleep(1)

    out_file = os.path.join(OUT_DIR, f"eval_{timestamp}.json")
    with open(out_file, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n=== Resultados guardados en {out_file} ===")


if __name__ == "__main__":
    main()
