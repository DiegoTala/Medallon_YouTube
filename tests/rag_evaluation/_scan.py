import re

path = "/home/diegotala42/Medallon_YouTube/.venv/lib/python3.14/site-packages/google/adk/models/gemini_llm_connection.py"
with open(path) as f:
    content = f.read()

# Buscar referencias a vertex, api_key, GOOGLE_*, VERTEX_*
for pat in [r".{120}vertex.{120}", r".{80}api_key.{80}", r".{80}GOOGLE_[A-Z_]+.{80}", r".{80}VERTEX_[A-Z_]+.{80}"]:
    for m in re.finditer(pat, content, re.IGNORECASE):
        print(">>", m.group(0).replace("\n", " ")[:250])
        print("---")
