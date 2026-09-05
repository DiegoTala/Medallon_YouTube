"""Middleware de la cadena de request (orden obligatorio, ver rag-fastapi-service).

1. IAP          -> verificación JWT
2. identidad    -> claims.sub como user_id
3. sanitización -> normaliza, quita controles, trunca
4. rate limit   -> 5/min por usuario
5. cuota diaria -> 30/día por usuario
6. caché        -> hit? responde y sale
"""
