project_id = "medallon-youtube"
region     = "us-central1"
zone       = "us-central1-a"

# Tag inmutable (SHA corto de commit) de la imagen publicada por deploy-release —
# nunca "latest" en producción (ver .claude/skills/deploy-release/SKILL.md).
image_tag = "1f346ac"

# Channel IDs (UC...) resueltos por scraping de solo lectura de la página pública
# del canal (sin API key, sin tocar infraestructura). Verificados contra el título
# de la página de cada canal:
#   Alesso              -> UC05i95k-w8CvrtZ-yGTob7A
#   ILLENIUM            -> UCv0tIDoaBZCTXQvVO4zosng
#   Swedish House Mafia  -> UC5HEq5U--O5nn134mizyCcw
#   Third Party          -> UCD0LPhlTZ9XANWXQh3t-VsQ
#   Martin Garrix         -> UC5H_KXkPbEsGs0tFt8R35mA
#   Porter Robinson       -> UCKKKYE55BVswHgKihx5YXew
#   DubVision             -> UCdbFjONDWTsdy8pgCsgvlxg
#   Avicii                -> UCPHjpfnnGklkRBBTd0k6aHg
#   Afrojack              -> UCmKm7HJdOfkWLyml-fzKlVg
#   Zedd                  -> UCPNokRZ9hacjIQ3IQL6HNUQ
channel_ids = [
  "UC05i95k-w8CvrtZ-yGTob7A", # Alesso
  "UCv0tIDoaBZCTXQvVO4zosng", # ILLENIUM
  "UC5HEq5U--O5nn134mizyCcw", # Swedish House Mafia
  "UCD0LPhlTZ9XANWXQh3t-VsQ", # Third Party
  "UC5H_KXkPbEsGs0tFt8R35mA", # Martin Garrix
  "UCKKKYE55BVswHgKihx5YXew", # Porter Robinson
  "UCdbFjONDWTsdy8pgCsgvlxg", # DubVision
  "UCPHjpfnnGklkRBBTd0k6aHg", # Avicii
  "UCmKm7HJdOfkWLyml-fzKlVg", # Afrojack
  "UCPNokRZ9hacjIQ3IQL6HNUQ", # Zedd
]
