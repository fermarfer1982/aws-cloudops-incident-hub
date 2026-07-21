# Selección reversible de Amazon Bedrock

## Estado y autoridad

**NO-GO PARA INFERENCIA BEDROCK REAL.** Esta selección es `proposed-disabled`,
reversible y no autoriza ejecución. ADR-013 permanece **Proposed** y el proyecto es
una validated laboratory reference architecture, **not production-ready**.

La configuración inerte está en
[`config/bedrock-model-selection.json`](../config/bedrock-model-selection.json).
El proveedor continúa desactivado; no se ha verificado acceso en ninguna cuenta.
Además, no hay autorización IAM y esta decisión no acepta términos ni producción.

## Selección provisional

| Campo | Propuesta |
| --- | --- |
| Proveedor / modelo | Amazon / Amazon Nova Lite |
| Región de origen | `eu-west-1` |
| Modelo regional | `amazon.nova-lite-v1:0` |
| Perfil geográfico | `eu.amazon.nova-lite-v1:0` |
| Endpoint / API | `bedrock-runtime` / `Converse` no streaming |
| Modalidad | texto de entrada y texto de salida |
| Estado | desactivado, IAM no autorizado, acceso de cuenta no verificado |

Nova Lite es provisional porque AWS lo mantiene activo, es compatible con Converse
y salida de texto, tiene perfil UE y bajo coste. Es suficiente como candidato para
resumir una fixture sintética, está controlado por AWS y evita inicialmente una
dependencia externa. La allowlist exacta hace reversible la decisión. Esto no
acredita calidad, acceso, permiso, aceptación de términos, inferencia, producción ni
aceptación de ADR-013.

## Residencia y enrutamiento

`eu-west-1` es solo la región de origen. El perfil UE puede procesar en
`eu-central-1`, `eu-north-1`, `eu-west-1` o `eu-west-3` según la tabla consultada; no
es inferencia estrictamente in-region y no se afirma que los datos permanezcan en
Irlanda. AWS indica que prompts y resultados pueden desplazarse dentro de la
geografía y que una retención por detección de abuso ocurriría en la región destino.

Los perfiles `global.*`, `us.*` y `apac.*` están prohibidos. La lista de destinos se
debe verificar de nuevo antes de ejecutar: un destino nuevo o no autorizado bloquea
la prueba y exige otra revisión de gobierno.

## Precio, presupuesto y cuotas

Snapshot documental consultado el **2026-07-21 UTC**, Geo/in-region Standard, USD
por millón de tokens: entrada **0,06 USD** y salida **0,24 USD**. Para una llamada:

`(1.000 / 1.000.000 × 0,06) + (300 / 1.000.000 × 0,24) = 0,000132 USD`.

El hard ceiling documental es **0,0002 USD**. Solo se propone una llamada, sin
reutilización automática ni retry tras respuesta válida; cualquier retry requiere
autorización expresa. No existe todavía control AWS de coste.

Para cross-region Nova Lite desde una región soportada distinta de las US
enumeradas, AWS publica 400 solicitudes/minuto y 400.000 tokens/minuto; la cuota de
tokens es ajustable y la de solicitudes no. Son techos del servicio, no presupuesto
ni autorización, y deben revisarse antes de ejecutar.

## Parámetros inertes

La propuesta fija `max_tokens=300`, `temperature=0`, `top_p=1`, una solicitud y no
streaming. Queda sin fallback de modelo o región y no permite tools, imágenes,
vídeo, documentos, caching, Bedrock Guardrails, application inference profile ni
retries automáticos. El timeout queda pendiente de alinear con Lambda. El cliente
funcional no se modifica.

## Acceso, términos e incertidumbres

AWS documenta acceso por defecto a modelos en regiones comerciales con los permisos
correctos, pero no se accedió a una cuenta: el acceso sigue sin verificar. La tarjeta
enlaza términos aplicables; su revisión y aceptación organizativa están pendientes.
El estado publicado es `Active`, pero disponibilidad, precio, cuota, destinos,
términos y abuso son mutables y deben revalidarse antes de la primera llamada.

## Fuentes oficiales consultadas

Consulta: **2026-07-21 UTC**.

- [Tarjeta oficial de Nova Lite](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-lite.html): estado, modalidades, Converse, endpoint, IDs, disponibilidad y términos.
- [Precios de Amazon Bedrock](https://aws.amazon.com/bedrock/pricing/): snapshot Standard Geo/in-region.
- [Perfiles compatibles](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-support.html): orígenes y destinos.
- [Inferencia geográfica](https://docs.aws.amazon.com/bedrock/latest/userguide/geographic-cross-region-inference.html): movimiento y residencia.
- [Acceso a modelos](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html): condiciones generales; no verifica esta cuenta.
- [Endpoints y cuotas](https://docs.aws.amazon.com/general/latest/gr/bedrock.html): cuotas cross-region.
- [Detección de abuso](https://docs.aws.amazon.com/bedrock/latest/userguide/abuse-detection.html): tratamiento y retención aplicable.

## Revisión obligatoria

Antes de ejecutar se requieren nueva verificación oficial, revisión de gobierno,
aceptación de términos, evidencia de acceso, aprobación humana, presupuesto y una
autorización IAM independiente. Hasta entonces: **NO-GO PARA INFERENCIA BEDROCK REAL**.
