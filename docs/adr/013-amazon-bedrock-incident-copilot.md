# ADR-013: Amazon Bedrock para Incident Copilot

- **Estado:** Proposed
- **Fecha:** 2026-07-14

## Contexto

AWS CloudOps Incident Hub ya recibe, almacena, consulta y notifica incidentes. La
referencia dispone de API protegida, almacenamiento en DynamoDB, observabilidad y
controles operacionales. CloudWatch, SNS, Amazon Q Developer y Slack fueron
validados mediante una prueba efímera y controlada de laboratorio.

El repositorio quiere evolucionar hacia una referencia reutilizable de IA
generativa aplicada a CloudOps. La primera capacidad propuesta, denominada **AWS
CloudOps Incident Copilot**, analizaría únicamente el contexto de un incidente y
devolvería un resumen estructurado. El proyecto sigue siendo una **validated
laboratory reference architecture** y está **not production-ready**.

Esta decisión es una propuesta de arquitectura. Amazon Bedrock no está integrado,
no se ha solicitado acceso a modelos y no existe evidencia de inferencia.

## Decisión propuesta

Usar Amazon Bedrock Runtime Converse API para un MVP estrictamente de solo lectura.
El copiloto podrá:

- consultar el incidente solicitado y resumir únicamente hechos presentes;
- generar resúmenes ejecutivo y técnico;
- identificar señales relevantes, información ausente y siguientes pasos;
- proponer hipótesis de causa separadas de los hechos;
- asociar cada hipótesis con evidencia y un nivel de confianza;
- mantener trazabilidad mediante `incident_id`, `request_id` y versión del prompt;
- devolver una respuesta JSON validada.

El MVP no podrá modificar incidentes o recursos AWS, cerrar alarmas, ejecutar
comandos, desplegar cambios, reiniciar servicios, eliminar recursos, ejecutar
remediaciones ni utilizar herramientas destructivas. No operará como agente
autónomo.

## Arquitectura inicial

```text
Cliente
  -> API Gateway
  -> Lambda/API de Incident Hub
  -> lectura controlada del incidente en DynamoDB
  -> servicio de orquestación GenAI
  -> Amazon Bedrock Runtime Converse API
  -> validación estricta de respuesta
  -> respuesta HTTP estructurada
```

Se propone una Lambda dedicada de orquestación GenAI para el MVP, invocada por la
ruta de API correspondiente y reutilizando modelos de dominio, autenticación y
acceso de lectura donde proceda. Frente a extender la Lambda existente, esta opción:

- aísla dependencias, timeout, concurrencia y fallos de inferencia;
- permite un rol IAM sin permisos de escritura y una allowlist Bedrock específica;
- evita que la latencia y el coste del modelo afecten a rutas ordinarias;
- escala y se limita de forma independiente;
- facilita métricas, presupuestos y desactivación separados;
- mantiene una frontera reutilizable para futuras capacidades GenAI.

El coste es una Lambda, configuración y superficie operacional adicionales, además
de cierta duplicación o extracción de código común. Para el MVP, el aislamiento y
el mínimo privilegio compensan esa complejidad. La implementación futura deberá
evitar duplicar lógica de negocio mediante interfaces compartidas y módulos
pequeños, no mediante un rol IAM común más amplio.

## Diseño interno propuesto

- `BedrockClient`: interfaz independiente del SDK.
- `BedrockConverseClient`: adaptador futuro del cliente `bedrock-runtime` y la
  operación `Converse`.
- `FakeBedrockClient`: doble determinista para pruebas sin llamadas reales.
- `IncidentSummaryService`: coordina lectura, redacción, prompt, inferencia,
  validación y telemetría.
- Repositorio de incidentes de solo lectura y limitado a atributos aprobados.
- Prompt versionado, esquema de entrada, esquema de salida y validador estricto.
- Manejo de errores que traduce fallos internos a respuestas HTTP controladas.
- Feature flag desactivada por defecto.
- Modelo y región configurables; el modelo debe pertenecer a una allowlist.
- Límites de contexto, salida, timeout y concurrencia.
- Métricas, trazabilidad y estimación de coste por solicitud.

No se fija un modelo concreto como decisión irreversible. La selección dependerá de
región, disponibilidad, calidad, coste, latencia, privacidad y evaluación con datos
sintéticos.

## Endpoint futuro

```http
POST /incidents/{incident_id}/ai-summary
```

Entrada opcional:

```json
{
  "summary_type": "technical",
  "include_recommendations": true
}
```

`summary_type` solo admitirá `technical` o `executive`. El cliente no podrá aportar
system prompts, un `model_id` arbitrario, parámetros de inferencia sin validar,
herramientas ni instrucciones libres que alteren el comportamiento del sistema.

## Contrato de salida

```json
{
  "incident_id": "string",
  "summary_type": "technical",
  "summary": "string",
  "observed_facts": ["string"],
  "probable_causes": [
    {
      "description": "string",
      "confidence": "low | medium | high",
      "supporting_evidence": ["string"]
    }
  ],
  "recommended_actions": ["string"],
  "missing_information": ["string"],
  "limitations": ["string"],
  "model_id": "string",
  "prompt_version": "string",
  "generated_at": "ISO-8601",
  "usage": {
    "input_tokens": 0,
    "output_tokens": 0,
    "total_tokens": 0
  },
  "latency_ms": 0
}
```

`probable_causes` son hipótesis, no hechos. `observed_facts` solo puede contener
datos del contexto y `supporting_evidence` debe proceder del incidente suministrado.
No se inventarán métricas, logs, eventos o despliegues; la ausencia de información
se declarará expresamente. `model_id` será un identificador no sensible obtenido de
configuración aprobada. La aplicación validará el JSON, sus tipos, límites, enums,
campos conocidos y fundamentación antes de devolverlo.

## Uso de Converse API

La futura implementación utilizará el cliente `bedrock-runtime` y `Converse`:

- `system` contendrá instrucciones versionadas separadas de los datos;
- `messages` contendrá el contexto estructurado y delimitado del incidente;
- `inferenceConfig` será controlado por la aplicación;
- `maxTokens` estará limitado y la temperatura será conservadora;
- `requestMetadata` podrá transportar correlación no sensible cuando proceda;
- `usage` y `metrics` alimentarán tokens, latencia y estimación de coste.

El primer MVP no utilizará `ConverseStream`, tool use ni parámetros libres del
proveedor.

## IAM

El rol de orquestación futuro:

- permitirá únicamente `bedrock:InvokeModel` sobre modelos o perfiles de inferencia
  explícitamente permitidos;
- aplicará una allowlist idéntica o más restrictiva en la aplicación;
- limitará DynamoDB a lectura de la tabla y atributos necesarios;
- permitirá solo la escritura imprescindible en logs y métricas;
- no tendrá permisos para modificar infraestructura, incidentes o remediaciones;
- no tendrá permisos administrativos de Bedrock ni credenciales persistentes.

Los despliegues seguirán realizándose exclusivamente mediante GitHub Actions, OIDC
y credenciales temporales. Una futura variante streaming tendría que evaluar y
autorizar por separado `bedrock:InvokeModelWithResponseStream`.

## Seguridad

- Feature flag desactivada por defecto y autenticación/autorización existentes.
- Validación de `incident_id`, tamaño máximo de entrada y límites de contexto.
- El contenido del incidente se trata como datos no confiables, no instrucciones.
- System prompt separado, contexto delimitado y prohibición explícita de obedecer
  instrucciones presentes en logs o mensajes.
- Neutralización o escapado cuando proceda y redacción de secretos, tokens, PII e
  identificadores sensibles antes de inferencia.
- Prohibición de registrar prompts completos o respuestas brutas sensibles.
- JSON estrictamente validado, campos desconocidos rechazados y enums permitidos.
- Timeout, gestión de throttling, límites de concurrencia y rate limiting.
- Auditoría mediante `incident_id` y `request_id` solo en logs/trazas controladas.
- Amazon Bedrock Guardrails podrá evaluarse en una fase posterior, pero complementa
  y no sustituye estos controles de aplicación.
- Cualquier futura acción de escritura exigirá aprobación humana.

## Privacidad y datos

Antes de implementar deben resolverse y aprobarse, en relación con WA-021:

- atributos del incidente permitidos para inferencia y su clasificación;
- presencia de PII, secretos o tokens y reglas de redacción/anonimización;
- retención y acceso a logs, región permitida y modelos permitidos;
- requisitos legales, contractuales y organizativos.

Este ADR no afirma que esas decisiones estén aprobadas.

## Coste y observabilidad

Se limitarán tokens de entrada y salida, tamaño de contexto, timeout y concurrencia.
Modelo y región serán configurables y la feature permanecerá desactivada por
defecto. Cada solicitud registrará de forma segura tokens de entrada, salida y
total, latencia, resultado, error, throttling y coste estimado.

Métricas propuestas:

- `AiSummaryRequests`, `AiSummarySuccess`, `AiSummaryErrors`;
- `AiSummaryValidationErrors`, `AiSummaryThrottles`;
- `AiSummaryInputTokens`, `AiSummaryOutputTokens`, `AiSummaryTotalTokens`;
- `AiSummaryLatency`, `AiSummaryEstimatedCost`.

Solo se usarán dimensiones de baja cardinalidad: `Environment`, `ModelFamily`,
`SummaryType` y `Result`. `incident_id` no será una dimensión de CloudWatch; junto
con `request_id`, se limitará a logs estructurados y trazas controladas.

Se estimará coste por resumen y por 1.000 resúmenes antes de habilitar pruebas AWS,
con budgets y alarmas. Se prohíben pruebas masivas fuera de un workflow manual,
controlado y acotado. El caching solo se evaluará después de privacidad y coste.

## Manejo de errores

La API distinguirá de forma controlada: feature desactivada, incidente no
encontrado, entrada demasiado grande, modelo no permitido, acceso denegado,
throttling, timeout, modelo no disponible, respuesta vacía, respuesta no JSON, JSON
inválido, incumplimiento de esquema, evidencia no fundamentada y error interno.

Nunca expondrá stack traces, prompts internos, políticas IAM, respuestas brutas del
proveedor ni información sensible.

## Alternativas consideradas

### Amazon Bedrock Converse API

Elegida para el MVP por su interfaz uniforme de mensajes, configuración común y
telemetría, manteniendo el modelo configurable.

### InvokeModel directamente

Ofrece control del formato nativo, pero acopla más la aplicación al contrato de
cada modelo y aporta poco valor para este caso conversacional estructurado.

### Bedrock Agents

Útil para planificación y herramientas, pero añade autonomía y superficie de
permisos incompatibles con el MVP de solo lectura sin herramientas.

### Bedrock Knowledge Bases

Adecuado para RAG sobre runbooks y postmortems. Se difiere hasta disponer de
gobierno de datos, corpus, citas y evaluación; el MVP solo usa el incidente.

### Proveedor de modelos externo

Puede ampliar la oferta, pero añade egress, integración, contratos, gobierno de
datos y credenciales fuera de la frontera AWS.

### Modelo local o self-hosted

Puede ofrecer control adicional, pero exige capacidad, parcheado, escalado,
observabilidad y operación que no se justifican para el primer laboratorio.

La decisión inicial es Converse API, sin agente autónomo, tool use, Knowledge Base,
RAG, escritura ni remediación automática.

## Consecuencias

### Positivas

- Interfaz uniforme para modelos compatibles y desacoplamiento parcial del modelo.
- Integración nativa con AWS, IAM, métricas de uso y trazabilidad.
- Evolución futura hacia guardrails, RAG y herramientas controladas.
- Experiencia demostrable de IA generativa aplicada a CloudOps.

### Negativas

- Coste por inferencia y latencia adicional.
- Disponibilidad regional y de modelos variable.
- Comportamiento probabilístico y riesgo de respuestas no fundamentadas.
- Necesidad de evaluaciones, privacidad y nuevos controles de seguridad.
- Dependencia de Bedrock y mantenimiento de prompts y datasets de evaluación.

## Criterio para aceptar el ADR

El estado permanecerá **Proposed** hasta que exista una implementación futura
validada con feature flag desactivada por defecto, IAM restringido, pruebas sin
inferencias reales por defecto, salida fundamentada y validada, telemetría segura,
coste documentado y una prueba AWS manual, efímera, controlada y destruida.
