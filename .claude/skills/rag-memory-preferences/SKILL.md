---
name: rag-memory-preferences
description: Preferencias de usuario en Firestore — se guardan SOLO por instrucción explícita y previa confirmación del agente, sin TTL. Úsalo al escribir o modificar la persistencia o la lectura de preferencias.
---

# rag-memory-preferences

## Alcance

Preferencias declaradas por el usuario y persistidas en `users/{user_id}` (PRD Fase 2 §9): idioma preferido, canales favoritos, temas de interés, preferencias de formato.

Es la única memoria **sin TTL** de Fase 2. Vive hasta que el usuario la cambie o la borre.

## La regla que define este skill

Dos condiciones, ambas obligatorias (PRD §9 y §16):

1. **El usuario lo pidió explícitamente.** "Me interesa mucho Fisher" es una observación, no una instrucción. "Recuerda que me interesa Fisher" sí lo es. Inferir preferencias del comportamiento está fuera de alcance.
2. **El agente confirmó antes de escribir.** Se le dice al usuario qué se va a guardar y se espera su confirmación en el mismo turno o el siguiente.

```
Usuario:  Recuerda que prefiero las respuestas en inglés.
Agente:   Voy a guardar "idioma preferido: inglés" en tus preferencias. ¿Lo confirmo?
Usuario:  Sí.
          -> recién aquí se escribe en Firestore
```

El criterio de aceptación del PRD §16 es literal: *"Las preferencias solo se guardan mediante instrucción explícita"*. Una escritura sin ese par instrucción-confirmación es un incumplimiento, aunque la preferencia inferida sea correcta.

## Documento

```
users/{user_id}
  preferred_language: str | None
  favorite_channels: list[str]
  topics_of_interest: list[str]
  format_preferences: dict
  updated_at: timestamp
```

Sin `expires_at`: la política TTL de [[rag-terraform-root]] aplica a los *collection groups* `messages` y `common_queries`, no al documento raíz del usuario. Un `expires_at` accidental aquí borraría las preferencias en silencio.

`favorite_channels` se valida contra los canales que existen en [[gold-rag-corpus]] antes de guardarse. Un canal inexistente guardado como favorito produce filtros que no devuelven nada, y el usuario no tiene forma de saber por qué.

## Efecto sobre las respuestas

Las preferencias modifican la salida, y eso tiene una consecuencia directa en el caché: **una respuesta personalizada por preferencias no se comparte entre usuarios** (PRD §10). Ver [[rag-response-cache]] — si una preferencia entró en la generación de una respuesta, el `user_id` es parte de su clave de caché.

`preferred_language` gana sobre la regla por defecto de idioma de [[rag-synthesis-citations]].

## Borrado

El usuario puede pedir que se olvide una preferencia, y eso se ejecuta con la misma explicitud: confirmar qué se borra, luego borrar. No hay borrado parcial silencioso ni "limpieza" automática.

## Invariantes

- **Instrucción explícita + confirmación previa.** Las dos, siempre.
- **Nunca se infieren preferencias** del historial de conversación ni de las consultas frecuentes de [[rag-memory-common-queries]] — esa colección es telemetría, no una fuente de preferencias.
- **Sin TTL.**
- **`user_id` del JWT verificado** de [[rag-iap-auth]], nunca de la entrada del request.
- **Los canales se validan contra el corpus** antes de persistirse.
- **Una respuesta personalizada nunca se sirve a otro usuario** — ver [[rag-response-cache]].

## Relación con otros skills

- Identidad: [[rag-iap-auth]].
- Convive con [[rag-memory-session]] y [[rag-memory-common-queries]] en la misma base de datos, con reglas de retención distintas.
- Afecta el idioma y el formato de [[rag-synthesis-citations]].
- Su efecto sobre el particionado del caché está en [[rag-response-cache]].
