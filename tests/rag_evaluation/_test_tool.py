import sys
sys.path.insert(0, "/home/diegotala42/Medallon_YouTube")
from google.cloud import bigquery
from rag_agent.tools.semantic_search import semantic_search

client = bigquery.Client(project="medallon-youtube")
r = semantic_search(
    client, "medallon-youtube", "gold",
    "¿Qué opinan los usuarios sobre los drops de Fisher?", top_k=5,
)
print(r)
