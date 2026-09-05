---
name: rag-iap-auth
description: Autenticación con IAP nativo de Cloud Run sin Load Balancer — habilitación, allowlist de las tres identidades, verificación del JWT en FastAPI y ruta de contingencia si el OAuth externo no es viable. Úsalo al escribir o modificar autenticación, identidad o control de acceso al servicio.
---

# rag-iap-auth

## Alcance

Cómo las tres identidades del PRD Fase 2 §2 acceden al servicio y cómo el backend **verifica** esa identidad en vez de confiar en ella.

## Estado del riesgo del PRD §11: resuelto, con una condición

El PRD marcaba como riesgo bloqueante confirmar que IAP nativo sobre Cloud Run existe sin Load Balancer.

> **Verificado 2026-09-04** ([Enable IAP for Cloud Run](https://docs.cloud.google.com/iap/docs/enabling-cloud-run), [Configure IAP for Cloud Run](https://docs.cloud.google.com/run/docs/securing/identity-aware-proxy-cloud-run)): **sí existe, es la vía recomendada por Google, y no tiene costo adicional.** Se habilita directamente sobre el servicio, protege el endpoint `run.app` en todos los caminos de ingreso, y no requiere provisionar Load Balancer. El PRD §11 no está bloqueado.

**Pero hay un bloqueo real para dos de los tres usuarios, y no está en IAP:**

> **Verificado 2026-09-04 contra el proyecto real.** `medallon-youtube` (número `180406516352`) pertenece a la organización **`talamantes.com.mx`** (ID `712010469336`, customer ID `C04fe1qyh`). Esa organización tiene **Domain Restricted Sharing activo**: la política `constraints/iam.allowedPolicyMemberDomains` está en efecto con `allowedValues: [C04fe1qyh]`, tanto a nivel de organización como efectiva sobre el proyecto.
>
> **Consecuencia: no se puede otorgar ningún binding IAM a una identidad fuera del directorio `talamantes.com.mx`.** Incluye `roles/iap.httpsResourceAccessor` para `medallon.rag.test01@gmail.com` y `medallon.rag.test02@gmail.com`. El binding lo rechaza la política de organización, en la capa de IAM — antes de que IAP entre en juego.

Esto es más profundo que el asunto del cliente OAuth. Un brand OAuth público resolvería la *autenticación* de una cuenta Gmail, pero la *autorización* falla igual: no hay forma de escribir el binding que le da acceso. Las dos cuentas Gmail del PRD §2 **no son viables** mientras esa política siga en efecto.

### Decisión (2026-09-04): identidades del dominio

**Diego decidió crear las dos cuentas de prueba dentro de `talamantes.com.mx`** — `medallon.rag.test01@` y `medallon.rag.test02@` — en lugar de las `@gmail.com` que fijaba el PRD §2, que ya está actualizado en consecuencia.

Lo que esa decisión compra:

1. **Cero excepciones de política.** Domain Restricted Sharing queda intacta. La alternativa era perforarla o explotar la brecha de grupos (ambas documentadas abajo como rutas descartadas).
2. **IAP se simplifica.** Identidades in-org funcionan con el cliente OAuth administrado por Google: **no hace falta cliente OAuth personalizado, ni brand externo, ni ningún paso manual de consola fuera de Terraform**. Tampoco aplica el modo Testing con su re-autenticación cada 7 días.
3. **Costo $0** — con una condición que sí puede costar caro, abajo.

### Costo de las identidades: $0, salvo un descuido caro

> **Verificado 2026-09-04** ([ediciones de Cloud Identity](https://docs.cloud.google.com/identity/docs/editions), [cómo funcionan las licencias](https://docs.cloud.google.com/identity/docs/how-to/how-licensing-works-for-cloud-identity)): la edición **gratuita** de Cloud Identity provee **50 licencias de usuario** por omisión, sin costo, y admite pedir más licencias gratuitas si se necesitan. Usa **licenciamiento por sitio**: no hay que asignar licencia manualmente — un usuario nuevo recibe la suya automáticamente. Cloud Identity Free convive con Google Workspace en el mismo dominio y **no requiere licencia de Workspace**: está pensada precisamente para usuarios que no necesitan Gmail, Drive ni Calendar. Es exactamente el caso de dos cuentas que solo deben autenticarse contra IAP.

**La trampa:** si el dominio tiene activado el **aprovisionamiento automático de licencias**, cada usuario nuevo recibe por omisión una licencia de **Google Workspace de pago**. Dos licencias de Workspace superan por sí solas el techo de $20 USD/mes de todo el proyecto — es decir, el descuido de tres clics costaría más que la infraestructura completa que este arnés protege.

Antes de crear las cuentas, en la Consola de Administración: verificar el estado del aprovisionamiento automático y, si está activo, desactivarlo o asignar explícitamente Cloud Identity Free. Confirmar después que las dos cuentas quedaron sin licencia de Workspace. Esto es un paso de [[cost-guardrail]] aunque no sea un recurso de GCP: el gasto es real y va contra el mismo bolsillo.

### Modo de falla confirmado: "Alcanzaste el límite de usuarios para Google Workspace Business Starter"

**Ocurrió en la práctica el 2026-09-04**, al primer intento de crear las cuentas. Es la trampa de arriba manifestándose, y es importante leer bien el mensaje: **no es un tope de usuarios del dominio**, es el tope de **asientos de Workspace**. La consola estaba intentando asignarle una licencia de pago a la cuenta nueva y no quedaban asientos libres.

La consecuencia útil: el error es una **protección accidental**. Si hubiera habido asientos disponibles, las dos cuentas se habrían creado con licencia de Workspace de pago y nadie se habría enterado hasta la factura.

**La corrección** ([desactivar el licenciamiento automático](https://support.google.com/cloudidentity/answer/7338389), [agregar licencias de Cloud Identity](https://docs.cloud.google.com/identity/docs/how-to/add-cloud-identity-licenses)): con el licenciamiento automático **desactivado**, un usuario nuevo recibe la licencia de **Cloud Identity Free** en lugar de la de Workspace — no consume asiento, y el límite de Business Starter deja de aplicar.

En la Consola de Administración, en orden. El ajuste **no está en Suscripciones** — ese fue un error de la primera versión de este skill, y buscarlo ahí hace perder tiempo:

1. Si Cloud Identity Free no aparece como suscripción: **Facturación → Comprar o actualizar → Cloud Identity → Cloud Identity Free** (costo $0). *Necesario pero no suficiente:* activarlo no apaga el licenciamiento automático, y el error persiste igual.
2. **Directorio → Unidades organizativas →** crear una UO dedicada (ej. `Cloud Identity`).
3. **Facturación → Configuración de licencias** (*License settings*) **→** seleccionar esa UO **→ Google Workspace Business Starter → desactivar**, anulando la configuración heredada del padre. Requiere el privilegio de gestión de licencias. Este es el paso que resuelve el error.
4. **Crear los usuarios dentro de esa UO** — en el diálogo de alta hay que cambiar la unidad organizativa explícitamente. Crearlos en la raíz hereda el licenciamiento automático de la raíz y **reproduce el mismo error**; es el tropiezo natural, porque la raíz es donde están todos los demás usuarios.
5. **Verificar en cada uno que no tiene licencia de Workspace asignada**, solo Cloud Identity Free.

Acotarlo a una UO en vez de apagarlo en la raíz mantiene el licenciamiento automático para las altas normales del dominio y confina el cambio a las cuentas de servicio del proyecto.

> Nota operativa: la doc advierte que una licencia asignada automáticamente puede tardar hasta 24 h en surtir efecto. Aplica al asignar, no al apagar — si la cuenta recién creada tarda en mostrar su licencia, no es señal de falla.

> **Salvedad si el dominio es de distribuidor.** El mensaje "comunícate con tu distribuidor" indica que la suscripción de Workspace se factura por un revendedor. Eso afecta la compra de **asientos de Workspace**, que es justo lo que aquí no se quiere comprar. Agregar Cloud Identity Free y desactivar el licenciamiento automático suelen seguir siendo autoservicio, pero si la sección de facturación está bloqueada por el revendedor, hay que pedírselo a él. Si eso resulta inviable, la ruta del **grupo del dominio con miembros externos** (apéndice de abajo) resuelve el acceso **sin crear ninguna cuenta nueva** — es la contingencia natural para este escenario.

### Pasos para habilitar el acceso

1. Desactivar el licenciamiento automático y crear los dos usuarios con Cloud Identity Free (manual, fuera de Terraform) — ver el modo de falla de arriba.
2. Verificar que ninguno recibió licencia de Workspace.
3. Declarar los tres bindings de `roles/iap.httpsResourceAccessor` en [[rag-terraform-root]] y aplicarlos vía [[approval-gate]].
4. Actualizar `ALLOWED_EMAILS` en el código con las tres direcciones.
5. Probar el acceso con las tres identidades — ver [[rag-deploy-service]].

## Apéndice: rutas descartadas para admitir cuentas Gmail

Se documentan porque el análisis costó trabajo y porque la decisión podría revisarse si algún día se necesita dar acceso a una identidad genuinamente externa. **Ninguna es el camino vigente.**

### Dos atajos evaluados: uno no sirve, el otro sí

**Invitados de Workspace (Workspace guests): no resuelven esto.** Verificado 2026-09-04 ([documentación de invitados](https://knowledge.workspace.google.com/admin/users/advanced/manage-workspace-guests)). Es una función de **colaboración**, no de identidad: los invitados quedan en una unidad organizativa dedicada de la que no se pueden mover, y su alcance son Chat, Drive, Meet y correo cifrado. La documentación no los contempla como principals de IAM de Google Cloud, y no pasan a formar parte del directorio bajo el customer ID a efectos de `allowedPolicyMemberDomains`. Si se quiere descartar del todo, la prueba es barata: crear un invitado e intentar el binding — pero no esperes que funcione.

**Grupo del dominio con miembros externos: sí funciona, y Google lo documenta como una brecha de su propio control.**

> **Verificado 2026-09-04** ([Domain-restricted sharing](https://docs.cloud.google.com/organization-policy/domain-restricted-sharing)): al evaluar si un grupo pertenece a un dominio permitido, **IAM solo evalúa el dominio del grupo, no el de sus miembros**. Un `roles/iap.httpsResourceAccessor` otorgado a `rag-usuarios@talamantes.com.mx` satisface Domain Restricted Sharing aunque ese grupo contenga cuentas `@gmail.com`. Google lo describe explícitamente como la vía por la que un administrador de proyecto puede eludir la restricción, y recomienda que el administrador de Workspace **impida que los grupos admitan miembros externos** para cerrarla.

Cómo leer eso con honestidad: el marco de Google es de **separación de funciones** — protege a la organización de un administrador de proyecto que no controla. Aquí el administrador de la organización y el del proyecto son la misma persona, así que no hay escalamiento de privilegios: es el dueño del control decidiendo dónde aplicarlo. Lo que sí queda es un costo de legibilidad: quien audite los bindings de IAM más adelante verá un grupo del dominio y **no podrá saber que contiene identidades externas** sin abrir el grupo. Si se toma esta ruta, el grupo se documenta como tal en `infra/APPROVALS.md` y su nombre lo delata (`rag-externos@`, no `rag-usuarios@`).

**Lo que el grupo NO resuelve:** solo cubre la *autorización*. La *autenticación* sigue necesitando el cliente OAuth personalizado con brand externo y arrastra el modo Testing con re-login cada 7 días (pasos 2 y 3 de abajo). El grupo ahorra el paso 1 — que era el más invasivo — pero no los otros.

### Ruta alterna: admitir cuentas Gmail de verdad

Si las cuentas deben ser `@gmail.com` sí o sí, es posible, pero cuesta cinco pasos y una excepción permanente de política. En orden:

**1. Levantar el bloqueo de IAM (el paso que decide todo lo demás).** Tres formas, de menor a mayor invasividad — la primera es el grupo descrito arriba, que evita tocar cualquier política:

- **Quirúrgica — `iam.managed.allowedPolicyMembers`.** La constraint *gestionada* (más nueva) acepta **principals individuales**, no solo dominios o customer IDs. Se puede autorizar exactamente esas dos direcciones y nada más:

  ```yaml
  name: projects/medallon-youtube/policies/iam.managed.allowedPolicyMembers
  spec:
    rules:
      - enforce: true
        parameters:
          allowedMemberSubjects:
            - "user:medallon.rag.test01@gmail.com"
            - "user:medallon.rag.test02@gmail.com"
  ```

- **Burda — relajar la constraint legada** `iam.allowedPolicyMemberDomains` en el proyecto. Abre el proyecto a **cualquier** identidad externa, no a dos. Se prefiere la quirúrgica siempre que sea viable.

  En ambos casos se sobrescribe a nivel de **proyecto** (`Override parent's policy`), nunca de organización: eso confina el radio de impacto a `medallon-youtube`. Requiere `roles/orgpolicy.policyAdmin` **otorgado en la organización**.

  > **Verificar antes de asumir (pendiente 2026-09-04):** la organización `talamantes.com.mx` aplica hoy la constraint **legada**. Google documenta ambos métodos como alternativas y recomienda elegir uno, pero **no encontré documentación oficial sobre qué ocurre cuando las dos están activas a la vez**. La lectura conservadora es que ambas se evalúan y ambas deben pasar — es decir, agregar la gestionada **no basta**: habría que sobrescribir también la legada en el proyecto. Confirmarlo empíricamente (intentar el binding y ver si lo rechaza) antes de dar la ruta por buena.

**2. Cliente OAuth personalizado con brand externo.** El cliente administrado por Google solo admite identidades in-org. Paso manual de consola, fuera de Terraform.

**3. Decidir el estado de publicación del app OAuth**, y aquí está el costo escondido:

| Estado | Verificación de Google | Tope de usuarios | Fricción para el usuario |
| :--- | :--- | :--- | :--- |
| Testing | no requerida | 100 | pantalla de "app no verificada" **y el token expira cada 7 días → re-login** |
| Publicado y verificado | requerida | sin tope | ninguna |

Para un chat de uso continuo, la re-autenticación cada 7 días en modo Testing es fricción real y recurrente, no un detalle de arranque. Publicar y verificar la elimina, a cambio de someter el app al proceso de verificación de Google.

**4. Otorgar `roles/iap.httpsResourceAccessor`** a las dos cuentas — solo funciona después del paso 1.

**5. Registrar el cambio.** La modificación de política de organización va por [[approval-gate]] con la gravedad que le corresponde (es un control de seguridad heredado, aunque se sobrescriba solo en este proyecto), se anota en `infra/APPROVALS.md`, y el PRD §2 se actualiza vía [[docs-maintenance]].

**Costo monetario: $0.** Lo que se paga es postura de seguridad y fricción operativa. Comparado con crear dos identidades en el dominio — que son cinco minutos, cero excepciones de política y cero re-logins — esta ruta solo se justifica si las cuentas Gmail son un requisito externo real, no una preferencia.

### Verificación (ya ejecutada, repetible)

```bash
gcloud projects describe medallon-youtube --format="value(projectNumber,parent.type,parent.id)"
gcloud organizations list
gcloud resource-manager org-policies describe constraints/iam.allowedPolicyMemberDomains \
  --project=medallon-youtube --effective
```

Repetir si cambia la política de la organización: es lo que determina qué identidades pueden entrar.

## Habilitación

IAP se activa sobre el servicio y el acceso se concede con `roles/iap.httpsResourceAccessor` a las tres identidades. Ambas cosas se declaran en Terraform ([[rag-terraform-root]]). Con identidades del dominio, el cliente OAuth administrado por Google basta: **no queda ningún paso de consola en esta capa**, salvo la creación misma de los dos usuarios.

Limitaciones verificadas que conviene tener presentes:

- **No se puede tener IAP en el servicio y en un Load Balancer a la vez.** Irrelevante aquí — el LB está fuera de alcance (PRD §4).
- **IAP agrega latencia.** Aceptable para un chat; no lo sería para un endpoint sensible a latencia.
- **Incompatible con Cloud CDN.**
- **Cloud Run aplica las políticas de IAP antes del control IAM sobre la service account de IAP**, y IAP reemplaza la identidad del llamador original. Un invocador de servicio a servicio que dependa de su propia autenticación puede romperse detrás de IAP.

## Verificación del JWT (el corazón de este skill)

El PRD §11 lo exige: *"El acceso a la aplicación no dependerá únicamente de headers no verificados"*.

IAP inyecta `x-goog-iap-jwt-assertion`, un JWT firmado. Existen también headers `x-goog-authenticated-user-*` sin firma: **esos no se usan para autorizar nada**. Son falsificables por cualquiera que alcance el servicio por otro camino, y su única razón de existir es la conveniencia.

```python
from fastapi import HTTPException, Request
from google.auth.transport import requests as ga_requests
from google.oauth2 import id_token

IAP_AUDIENCE = f"/projects/{PROJECT_NUMBER}/locations/{REGION}/services/{SERVICE_NAME}"
# PROJECT_NUMBER de medallon-youtube = 180406516352 (verificado 2026-09-04)
IAP_CERTS_URL = "https://www.gstatic.com/iap/verify/public_key"
ALLOWED_EMAILS = frozenset({
    "diego@talamantes.com.mx",
    "medallon.rag.test01@talamantes.com.mx",
    "medallon.rag.test02@talamantes.com.mx",
})

def authenticate(request: Request) -> str:
    assertion = request.headers.get("x-goog-iap-jwt-assertion")
    if not assertion:
        raise HTTPException(status_code=401, detail="Falta la aserción de IAP")
    try:
        claims = id_token.verify_token(
            assertion, ga_requests.Request(),
            audience=IAP_AUDIENCE, certs_url=IAP_CERTS_URL,
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Aserción de IAP inválida") from exc

    email = claims.get("email")
    if email not in ALLOWED_EMAILS:
        raise HTTPException(status_code=403, detail="Identidad no autorizada")
    return claims["sub"]      # identificador estable -> user_id interno
```

Tres detalles que no son opcionales:

- **`audience` con el formato exacto de Cloud Run:** `/projects/{PROJECT_NUMBER}/locations/{REGION}/services/{SERVICE_NAME}`. Es distinto del formato de Load Balancer (`/projects/{N}/global/backendServices/{ID}`). Y es `PROJECT_NUMBER`, no `PROJECT_ID`. Sin `audience`, un JWT válido emitido para **otro** servicio protegido por IAP pasaría la verificación.
- **`certs_url` apuntando a las llaves de IAP**, no a las de Google en general.
- **`sub`, no `email`, como `user_id` interno.** `sub` es el identificador estable; un correo puede reasignarse. Todo lo que se guarde bajo `users/{user_id}` en [[rag-memory-session]], [[rag-memory-preferences]] y [[rag-memory-common-queries]] cuelga de esta decisión, así que cambiarla después implica migrar datos.

La allowlist en código es **defensa en profundidad**, no el control principal: el control es el IAM de IAP. Tener ambos significa que un binding IAM mal aplicado no basta para entrar.

## Ruta de contingencia (si el OAuth externo no resulta viable)

Solo si la verificación previa demuestra que las cuentas Gmail no pueden autorizarse vía IAP. **Sin Load Balancer**, que sigue fuera de alcance:

Cloud Run con `--no-allow-unauthenticated` y sin IAP; se concede `roles/run.invoker` únicamente a las tres identidades; el cliente envía un ID token de Google en `Authorization: Bearer`, y FastAPI lo verifica con `id_token.verify_oauth2_token`, comprobando `email`/`email_verified` contra la misma allowlist.

Es un downgrade real de experiencia: no hay pantalla de login gestionada, el cliente debe obtener y renovar el token por su cuenta. Por eso es contingencia y no alternativa. **Activarla es un cambio de arquitectura**: se documenta en `docs/PRD_Fase2.md` vía [[docs-maintenance]] antes de implementarse.

## Invariantes

- **Ninguna decisión de autorización sobre un header sin firma.** Nunca `x-goog-authenticated-user-email`.
- **`audience` siempre presente y con el formato de Cloud Run.**
- **`sub` como `user_id` interno**, en todas las colecciones de Firestore.
- **Allowlist en IAM y en código**, las dos.
- **Toda identidad no autorizada recibe 403**, sin filtrar si existe o no.
- **Toda identidad con acceso debe pertenecer a `talamantes.com.mx`** mientras Domain Restricted Sharing esté activo. Verificar la política antes de agregar cualquier usuario nuevo.
- **Las cuentas del dominio se crean con Cloud Identity Free, nunca con licencia de Workspace.** Verificarlo después de crearlas: dos licencias de pago exceden el techo del proyecto entero.
- **La creación de identidades se registra en `infra/APPROVALS.md`** aunque sea manual y no la ejecute Terraform, porque cambia quién puede entrar al sistema.
- **La ruta de contingencia no se activa sin actualizar el PRD.**

## Relación con otros skills

- Los recursos de IAP y sus bindings: [[rag-terraform-root]].
- La identidad que devuelve alimenta [[rag-quota-limits]] y las tres skills de memoria.
- Su posición en la cadena: [[rag-fastapi-service]].
- Verificación de estado real del proyecto: [[gcloud-diagnostics]].
- El despliegue que habilita IAP en el servicio: [[rag-deploy-service]].
