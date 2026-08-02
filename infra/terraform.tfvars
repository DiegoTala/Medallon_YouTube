project_id = "medallon-youtube"
region     = "us-central1"
zone       = "us-central1-a"

# Channel IDs (UC...) resueltos por scraping de solo lectura de la página pública
# del canal (sin API key, sin tocar infraestructura). Verificados contra el título
# de la página de cada canal:
#   Alesso              -> UC05i95k-w8CvrtZ-yGTob7A
#   ILLENIUM            -> UCv0tIDoaBZCTXQvVO4zosng
#   Swedish House Mafia  -> UC5HEq5U--O5nn134mizyCcw
#   Third Party          -> UCD0LPhlTZ9XANWXQh3t-VsQ
#   Martin Garrix         -> UC5H_KXkPbEsGs0tFt8R35mA
channel_ids = [
  "UC05i95k-w8CvrtZ-yGTob7A", # Alesso
  "UCv0tIDoaBZCTXQvVO4zosng", # ILLENIUM
  "UC5HEq5U--O5nn134mizyCcw", # Swedish House Mafia
  "UCD0LPhlTZ9XANWXQh3t-VsQ", # Third Party
  "UC5H_KXkPbEsGs0tFt8R35mA", # Martin Garrix
]
