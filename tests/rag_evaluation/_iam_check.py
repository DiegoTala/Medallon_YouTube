import subprocess
import requests
import json

GCLOUD = "/home/diegotala42/google-cloud-sdk/bin/gcloud"

r = subprocess.run([GCLOUD, "auth", "print-access-token"], capture_output=True, text=True)
token = r.stdout.strip()
headers = {"Authorization": "Bearer " + token}

# 1. IAM de la conexión Vertex (bigquery connections)
url = "https://bigqueryconnection.googleapis.com/v1/projects/medallon-youtube/locations/us-central1/connections/vertex-ai-connection:getIamPolicy"
resp = requests.post(url, headers=headers, json={}, timeout=30)
print("=== Conexión Vertex IAM ===")
print(resp.status_code, resp.text[:800])

# 2. IAM del dataset gold (vía API)
url2 = "https://bigquery.googleapis.com/bigquery/v2/projects/medallon-youtube/datasets/gold"
resp2 = requests.get(url2, headers=headers, timeout=30)
data = resp2.json()
print("\n=== Dataset gold access ===")
for entry in data.get("access", []):
    print(entry)
