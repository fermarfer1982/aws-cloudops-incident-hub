# Gobierno de datos para GenAI

## Estado y autoridad

- **Estado:** Aprobado para el alcance sintético de laboratorio al fusionarse esta política.
- **Control relacionado:** WA-021.
- **Propietario:** Repository owner / laboratory administrator.

La fusión de esta política constituye la aprobación del propietario del laboratorio.
El laboratorio es administrado por una sola persona y no existe segregación
independiente de funciones. Esta aprobación no constituye aprobación jurídica, de
privacidad o de seguridad para producción. Antes de utilizar datos reales será
obligatoria una aprobación organizativa independiente.

## Alcance autorizado

La política permite únicamente preparar una futura prueba con un solo incidente,
completamente sintético, creado desde una fixture versionada y revisada, y una sola
invocación. Su único objeto sería validar técnicamente un resumen asistido, sin
decisiones automáticas, acciones correctivas ni persistencia del contenido generado.

Esta política y la PR que la introduce no autorizan ejecutar la inferencia.

## Finalidad

> Generar un resumen consultivo de un incidente sintético para validar de forma
> técnica el cliente, el esquema, el grounding, los límites, la telemetría
> saneada y el ciclo desplegar-validar-destruir.

Quedan prohibidas las decisiones automáticas, la remediación, las recomendaciones
ejecutables, el uso laboral, disciplinario o de evaluación de personas, el
entrenamiento, el fine-tuning, RAG, caching, la analítica secundaria y cualquier
reutilización del contenido.

## Clasificación

| Clase | Definición | Permitida en primera prueba |
|---|---|---|
| Pública | Información publicable sin restricciones | No necesaria |
| Interna | Información operativa no pública | No |
| Confidencial | Información empresarial sensible | No |
| Restringida | PII, credenciales, secretos o datos regulados | No |
| Sintética de laboratorio | Datos inventados, sin relación con personas, sistemas o empresas reales | Sí |

La única clasificación admitida es **Sintética de laboratorio**.

## Allowlist exacta de atributos

| Atributo | Tipo permitido | Restricción |
|---|---|---|
| `source` | string | Valor sintético fijo de una allowlist versionada |
| `site` | string | Etiqueta sintética; nunca una sede real |
| `message` | string | Texto fijo de la fixture sintética; sin entrada libre |
| `value` | number o null | Valor sintético acotado; nunca texto |

Ningún atributo adicional puede enviarse. Cualquier campo no incluido debe
eliminarse antes de construir el prompt y, si llega a la frontera de validación,
debe causar rechazo. Campo no allowlisted o clasificación desconocida implica
rechazo antes de la inferencia.

`incident_id` puede utilizarse para correlación técnica interna, pero no debe
enviarse al modelo ni incluirse en la evidencia. `source`, `site` y `message` no
pueden proceder de una petición libre durante la primera prueba. La fixture será
inmutable durante el workflow. Cambiar esta allowlist requiere una nueva PR de
gobierno.

No se admiten silenciosamente hostname, IP, email, usuario, nombre, teléfono,
dirección, dominio, URL, número de serie, Account ID, ARN, ticket real,
identificador de cliente ni texto empresarial.

## Datos prohibidos

Se prohíben datos empresariales o incidentes reales; datos personales o categorías
especiales; nombres, emails, teléfonos y direcciones; IP, hostname, dominio e
identificadores reales de dispositivos; credenciales, access keys, tokens, cookies,
claves privadas, client secrets y connection strings; Account IDs, ARN y URLs
internas; logs, stack traces, payloads reales y outputs CloudFormation; prompts o
respuestas anteriores; contenido de tickets, correo, Slack o monitorización; y todo
dato con clasificación desconocida.

> Campo no allowlisted o clasificación desconocida implica rechazo antes de la
> inferencia.

## PII y secretos

La redacción de patrones conocidos, la detección de PII y la clasificación previa
son controles distintos. La redacción actual no constituye detección suficiente de
PII.

La primera prueba exigirá una fixture sintética revisada, allowlist positiva y un
detector preventivo de patrones prohibidos. Ante un posible secreto, PII o dato
real, no se sustituye silenciosamente: no se invoca el modelo, la ejecución falla
de forma cerrada, se eliminan temporales, se ejecuta destroy y solo se conserva un
código de fallo saneado. El valor detectado nunca se registra.

## Minimización

El contexto se construirá exclusivamente con `source`, `site`, `message` y `value`.
Los valores vacíos no se sustituyen por otros campos. No se envía el objeto completo
de DynamoDB, metadatos internos, claves, índices, timestamps técnicos ni
identificadores. No existe fallback hacia la serialización del incidente completo.

## Región y transferencia

Esta política no aprueba todavía ninguna región ni modelo. Toda futura inferencia
deberá usar una única región aprobada y compatible con la residencia del
laboratorio. La disponibilidad de Amazon Bedrock, Converse y el modelo se verificará
oficialmente en una PR posterior. Cross-region inference queda prohibida por
defecto, incluidos inference profiles con procesamiento multirregión, hasta una
aprobación específica.

## Retención

| Elemento | Persistencia permitida | Retención |
|---|---|---|
| Fixture sintética versionada | Sí | Histórica en Git |
| Prompt y contexto construidos | No | Memoria durante la invocación |
| Respuesta bruta | No | Memoria hasta validación y revisión autorizada |
| Texto generado | No | No logs, no artifacts, no Git |
| Temporales de GitHub Actions | Solo durante el job | Eliminación bajo `always()` |
| Logs Lambda | Solo metadatos saneados | Log group efímero y destruido |
| Artifact técnico | Solo evidencia saneada | Máximo 7 días |
| Evidencia JSON versionada | Sí, sin contenido | Histórica en Git |
| Archivos en `mirofish` | No | Deben quedar ausentes |

La evidencia saneada puede contener métricas y estados, nunca texto generado.

## Borrado y cleanup

Los temporales tendrán permisos restrictivos y se borrarán tanto en éxito como en
fallo. Prompt y raw response se eliminarán antes de subir evidencia. El destroy se
ejecutará de forma incondicional y la comprobación final verificará la ausencia del
stack, la Lambda y el log group. El workflow fallará si no demuestra cleanup.

Una persistencia inesperada activa el procedimiento de incidente y prohíbe relanzar
automáticamente la ejecución con sospecha de exposición.

## Logging y telemetría

Solo se permiten versión de prompt, alias saneado de familia de modelo, resultado
técnico, estado HTTP, indicadores de JSON, esquema y grounding válidos, contador de
afirmaciones no soportadas, tokens, latencia, coste estimado, códigos de error
saneados y estados de destroy y cleanup.

Se prohíben prompt, system prompt, contexto, fixture completa, respuesta bruta,
texto generado, evidencia textual, payload, identificadores AWS, credenciales y
datos personales o empresariales.

## Acceso humano y responsabilidad

| Rol | Responsabilidad |
|---|---|
| Propietario del laboratorio | Aprobar política, ejecución y techo de coste |
| Environment reviewer | Autorizar el workflow manual |
| Workflow | Aplicar controles técnicos y cleanup |
| Revisor humano autorizado | Evaluar todas las afirmaciones antes de aceptar la ejecución |
| Operador | No ejecutar acciones derivadas automáticamente |

En el laboratorio una persona puede ejercer varios roles; esto no equivale a
segregación de funciones. Producción exige separación y aprobación organizativa.
La salida es consultiva y toda decisión continúa bajo responsabilidad humana.

El mecanismo seguro de revisión humana de la respuesta deberá definirse antes de
la prueba y no podrá imprimirla en logs ni subirla como artifact sin protección.

## Auditoría

Se registrarán de forma saneada: commit, workflow run, fecha, región aprobada,
versión de política, versión de prompt, alias saneado de modelo, autorización del
Environment, resultado técnico, revisión humana, destroy y cleanup. No se
versionarán el nombre personal del reviewer ni su identificador interno.

## Incidentes de datos

La detección de PII, secreto o atributo no allowlisted, una persistencia inesperada,
un log con contenido, un artifact con respuesta o un cleanup incompleto obliga a:

1. Bloquear la inferencia o detener el workflow.
2. Evitar imprimir el contenido.
3. Eliminar temporales.
4. Ejecutar destroy.
5. Verificar ausencia.
6. Registrar únicamente un estado saneado.
7. No reintentar.
8. Abrir una revisión de seguridad antes de otra ejecución.

## Revisión de la política

Requieren una nueva aprobación: datos reales; cambios de atributos, finalidad,
región o retención; cross-region inference; persistencia de respuestas; RAG;
caching; Guardrails; streaming; herramientas; acciones automáticas; producción; o
cambios de principal o del mecanismo de revisión humana.

## Cierre de WA-021

WA-021 queda completada al fusionarse esta política únicamente para la
clasificación y retención del caso sintético de laboratorio. El cierre no autoriza
inferencia ni datos reales; no aprueba región o modelo; `bedrock:InvokeModel` no se
concede; no habilita Amazon Bedrock; no cambia ADR-013 y no implica production
readiness. El proyecto permanece **not production-ready** y el veredicto continúa
**NO-GO PARA INFERENCIA BEDROCK REAL**.
