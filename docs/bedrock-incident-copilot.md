# AWS CloudOps Incident Copilot — diseño propuesto

## 1. Visión del producto

AWS CloudOps Incident Copilot es una evolución propuesta de AWS CloudOps Incident
Hub para transformar el contexto acotado de un incidente en un análisis
estructurado, trazable y de solo lectura mediante Amazon Bedrock. Existe un núcleo
local, un adaptador de aplicación testeable para Converse API y un shell de
infraestructura cerrado expresado en CDK, pero no existe un modelo aprobado, acceso
al modelo ni evidencia de inferencia real. El shell cerrado y efímero sí fue
desplegado y validado en AWS.
La referencia continúa validada únicamente como laboratorio y no está preparada
para producción.

## Implementation status

### Implementado

- Modelos estrictos de entrada, payload interno y respuesta.
- Prompt builder versionado y separado del contexto no confiable.
- Redacción inicial de claves y patrones de secretos.
- Hechos observados y allowlist de evidencia construidos de forma determinista.
- Validación de esquema, tamaño, campos conocidos y grounding.
- `FakeBedrockClient` determinista y `DisabledBedrockClient` cerrado por defecto.
- `BedrockConverseClient` con SDK inyectable, límites, timeouts y allowlist de modelo.
- Endpoint FastAPI local con inyección de dependencias y errores estables.
- Tests unitarios y de API sin red, AWS, credenciales ni sleeps.
- Feature flag desactivada por defecto.
- Dataset sintético versionado y evaluador local determinista.
- Informe JSON reproducible y CLI para predicciones guardadas.
- Validaciones estructurales, grounding exacto, causas permitidas, completitud y
  afirmaciones prohibidas.
- Lambda GenAI dedicada e integración independiente con la HTTP API.
- Scope Cognito dedicado `cloudops-incident-hub/incidents.summarize`.
- Rol IAM independiente limitado a `dynamodb:GetItem` sobre la tabla de incidentes.
- Uso del pool de concurrencia no reservada, log group separado y alarmas Lambda
  nativas.
- Configuración cerrada con `AI_SUMMARY_ENABLED=false` y
  `AI_SUMMARY_PROVIDER=disabled`, sin permisos Bedrock.
- Workflow AWS manual y controlado para el shell cerrado.
- Despliegue AWS efímero, IAM, autenticación y estado desactivado validados.
- Destroy, cleanup y evidencia saneada verificados.

### Pendiente

- Región Bedrock aprobada, modelo o inference profile permitido y acceso al modelo.
- `bedrock:InvokeModel` de mínimo privilegio e inferencia real.
- Métricas custom de CloudWatch y Amazon Bedrock Guardrails.
- Selección y aprobación de modelo, acceso al modelo e inferencias reales.
- Evaluación semántica y groundedness con evaluadores reales.
- Coste, latencia y métricas de tokens reales de Amazon Bedrock.
- Decisiones WA-021 sobre clasificación, privacidad y retención.
- Cambio de ADR-013 de **Proposed** a **Accepted** tras evidencia real.
- Production readiness.

Este estado completa únicamente la validación AWS del shell cerrado. El modo fake
usa datos sintéticos y no representa inferencia real.
El arnés local evalúa un contrato determinista; no valida la calidad de un LLM ni
reemplaza evaluación humana, Bedrock Evaluations o pruebas con modelos reales.
Esta infraestructura es un shell cerrado validado mediante synth, tests locales y
un despliegue AWS efímero; no constituye una integración Amazon Bedrock validada.
Las métricas de tokens, latencia de proveedor, coste, grounding, validación y
errores del provider requieren cambios posteriores de aplicación.

## 2. Problema que resuelve

Durante un incidente, la información disponible puede ser dispersa y difícil de
priorizar. El copiloto reduciría el tiempo de lectura inicial, separaría hechos de
hipótesis, señalaría información ausente y propondría siguientes pasos sin ejecutar
acciones ni sustituir el juicio del operador.

## 3. Usuarios objetivo

- Operadores y personal on-call que necesitan una primera síntesis.
- Responsables técnicos que necesitan un resumen ejecutivo o técnico.
- Equipos de plataforma y SRE que evalúan patrones y postmortems.
- Revisores de una arquitectura de laboratorio de GenAI aplicada a CloudOps.

## 4. Casos de uso

- Resumen ejecutivo y resumen técnico del incidente.
- Lista de hechos observados.
- Hipótesis de causa con evidencia y confianza.
- Próximos pasos recomendados y datos ausentes.
- Borrador de postmortem, siempre marcado explícitamente como borrador.

## 5. Casos fuera de alcance

- Remediación automática o modificación de recursos AWS.
- Ejecución de comandos, cierre de incidentes o cambios de configuración.
- Despliegues, reinicios o eliminación de recursos.
- Agente autónomo, herramientas, RAG o Knowledge Bases.
- Análisis libre de todos los logs de una cuenta.
- Conversaciones multi-turno, streaming y uso productivo.

## 6. Arquitectura propuesta

```text
Cliente
  -> API Gateway
  -> Lambda/API de Incident Hub
  -> lectura controlada en DynamoDB
  -> Lambda dedicada de orquestación GenAI
       -> IncidentSummaryService
       -> BedrockClient / BedrockConverseClient
       -> validador de respuesta
  -> Amazon Bedrock Runtime Converse API
  -> JSON validado
  -> respuesta HTTP
```

Se recomienda una Lambda GenAI dedicada. Aísla permisos, timeout, concurrencia,
dependencias, costes y fallos del camino API ordinario. Reutilizará interfaces y
modelos de dominio sin compartir un rol IAM amplio. Extender la Lambda existente
reduciría inicialmente recursos y saltos, pero mezclaría perfiles de latencia,
escalado y permisos y aumentaría el impacto de fallos de inferencia.

## 7. Arquitectura por fases

### Fase 1 — MVP de resumen

Converse API, endpoint único, contexto limitado al incidente, JSON validado, solo
lectura, cliente simulado en pruebas y feature flag desactivada por defecto.

### Fase 2 — Evaluación y guardrails

Dataset sintético, evaluaciones de groundedness, relevancia, completitud, precisión
estructural e invenciones; evaluación de Amazon Bedrock Guardrails, modelos, coste
y latencia.

### Fase 3 — RAG

Runbooks, ADR, postmortems y documentación operativa con citas y metadatos mediante
Bedrock Knowledge Bases o RAG equivalente, solo tras aprobar gobierno de datos.

### Fase 4 — Herramientas de diagnóstico

Solo lectura: `get_incident`, `get_alarm_history`, `get_metric_summary`,
`get_recent_deployments`, `search_runbooks`, `compare_performance_baseline` y
`find_similar_incidents`.

### Fase 5 — Acciones controladas

Solo tras una decisión posterior: aprobación humana obligatoria, IAM separado,
allowlist, auditoría, rollback y feature flags desactivadas. Nunca se incluirán
implícitamente en el rol de solo lectura.

## 8. Diseño del MVP

Componentes conceptuales:

- `BedrockClient`, contrato estable para inferencia.
- `BedrockConverseClient`, adaptador del cliente `bedrock-runtime`.
- `FakeBedrockClient`, respuestas deterministas para pruebas.
- `IncidentSummaryService`, orquestación de lectura a respuesta.
- Repositorio de incidentes estrictamente de solo lectura.
- Prompt builder versionado y determinista.
- Esquemas de entrada/salida y validador estricto.
- Mapeador de errores y telemetría segura.

Configuración propuesta: feature flag, región, modelo permitido, versión de prompt,
tokens máximos, tamaño de contexto, temperatura conservadora, timeout,
concurrencia/rate limit y parámetros de coste. No se elige todavía un modelo
concreto de forma irreversible.

## 9. Flujo de petición

1. API Gateway aplica autenticación, autorización, throttling y límites.
2. La aplicación valida `incident_id` y el cuerpo opcional.
3. Si la feature está desactivada, devuelve una respuesta controlada sin inferir.
4. El repositorio lee solo los atributos aprobados del incidente.
5. Se redactan secretos/PII y se verifica el tamaño máximo.
6. El prompt builder separa system prompt y contexto no confiable.
7. El servicio llama a `BedrockClient.converse` con configuración controlada.
8. Se extraen contenido, `usage` y `metrics` sin registrar datos sensibles.
9. El validador analiza JSON, esquema, límites y fundamentación.
10. Se emiten métricas y logs correlacionados y se devuelve HTTP estructurado.

## 10. Contrato de entrada

Endpoint futuro:

```http
POST /incidents/{incident_id}/ai-summary
```

```json
{
  "summary_type": "technical",
  "include_recommendations": true
}
```

El cuerpo es opcional, tiene tamaño máximo y rechaza campos desconocidos.
`summary_type` admite solo `technical` o `executive`. No admite system prompts,
`model_id`, parámetros arbitrarios, herramientas ni instrucciones libres.

## 11. Contrato de salida

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

`model_id` procede de configuración aprobada y no debe revelar información
sensible. La aplicación, no el modelo, completa o verifica metadatos como
`incident_id`, modelo, prompt, tiempo, uso y latencia.

## 12. Diseño del prompt

El prompt será versionado, revisable y construido por código:

- `system`: rol de analista de solo lectura, contrato JSON y prohibiciones.
- `messages`: un bloque de contexto etiquetado como datos no confiables.
- Instrucción de usar exclusivamente el contexto y declarar ausencias.
- Separación explícita de hechos, hipótesis, evidencia y recomendaciones.
- Prohibición de seguir instrucciones embebidas en logs o mensajes.
- Límites de longitud y cardinalidad por campo.

La aplicación controla `inferenceConfig`, `maxTokens` y una temperatura
conservadora. Puede usar `requestMetadata` no sensible para correlación apropiada y
recoge `usage` y `metrics`. El MVP no utiliza `ConverseStream`.

## 13. Separación entre hechos e hipótesis

- `observed_facts`: afirmaciones directamente sustentadas por el contexto.
- `probable_causes`: hipótesis explícitas, nunca hechos confirmados.
- `supporting_evidence`: referencias textuales o estructurales al incidente.
- `missing_information`: datos necesarios que no están disponibles.
- `limitations`: restricciones que afectan la interpretación.

No se inventan métricas, logs, eventos, alarmas ni despliegues. Una hipótesis sin
evidencia se rechaza o se degrada y se declara la insuficiencia de datos.

## 14. Validación de respuestas

El validador futuro deberá:

1. Rechazar salida vacía, no JSON o JSON inválido.
2. Rechazar campos desconocidos, tipos incorrectos y enums fuera de allowlist.
3. Aplicar máximos de longitud, elementos y profundidad.
4. Verificar `incident_id` y `summary_type` contra la petición.
5. Verificar que cada evidencia existe en el contexto saneado.
6. Detectar afirmaciones sin soporte mediante reglas y evaluación.
7. Añadir metadatos fiables desde la aplicación.
8. Fallar de forma cerrada sin devolver la respuesta bruta.

## 15. Seguridad

- Feature flag desactivada por defecto.
- Autenticación y autorización existentes; validación estricta de `incident_id`.
- Máximos de cuerpo, contexto, salida, timeout, concurrencia y tasa.
- Contenido del incidente tratado como no confiable y delimitado estructuralmente.
- System prompt separado; instrucciones embebidas nunca se obedecen.
- Neutralización/escape cuando corresponda y redacción previa de secretos/PII.
- No registrar prompts completos, contexto sensible ni respuestas brutas.
- JSON estricto, rechazo de campos desconocidos y allowlists.
- Gestión explícita de throttling y auditoría por `incident_id`/`request_id`.
- Guardrails podrá añadirse después, sin sustituir validación, IAM ni redacción.
- Aprobación humana obligatoria para cualquier futura escritura.

## 16. Privacidad

Antes de implementar, WA-021 deberá informar decisiones aún no aprobadas:

- atributos permitidos, clasificación y finalidad;
- presencia de PII, secretos o tokens;
- anonimización/redacción y retención de logs;
- región y modelos permitidos;
- requisitos legales, contractuales y organizativos.

La minimización de datos precede a la inferencia. No se habilitará caching hasta
evaluar privacidad, invalidación y coste.

## 17. IAM

- `bedrock:InvokeModel` únicamente sobre modelos/perfiles permitidos.
- Allowlist equivalente en configuración de aplicación.
- Lectura DynamoDB limitada a tabla, clave y atributos aprobados.
- Escritura mínima en logs y métricas.
- Sin escritura de incidentes, infraestructura o remediación.
- Sin administración Bedrock ni credenciales persistentes.
- Despliegues solo por GitHub Actions, OIDC y credenciales temporales.

Streaming requeriría una decisión y evaluación separadas para
`bedrock:InvokeModelWithResponseStream`.

## 18. Observabilidad

Métricas propuestas:

- `AiSummaryRequests`, `AiSummarySuccess`, `AiSummaryErrors`;
- `AiSummaryValidationErrors`, `AiSummaryThrottles`;
- `AiSummaryInputTokens`, `AiSummaryOutputTokens`, `AiSummaryTotalTokens`;
- `AiSummaryLatency`, `AiSummaryEstimatedCost`.

Dimensiones de baja cardinalidad: `Environment`, `ModelFamily`, `SummaryType` y
`Result`. `incident_id` nunca será dimensión CloudWatch. `incident_id` y
`request_id` se usarán solo en logs estructurados y trazas controladas, con modelo,
prompt version, resultado, tokens y latencia, sin contenido sensible.

## 19. Gestión de errores

| Condición | Comportamiento propuesto |
|---|---|
| Feature desactivada | Respuesta controlada; no invocar Bedrock |
| Incidente no encontrado | `404` sin revelar otros datos |
| Entrada/contexto grande | `413` o error de dominio estable |
| Modelo no permitido | Fallo cerrado y alerta de configuración |
| Acceso denegado | Error interno controlado y métrica |
| Throttling | Respuesta reintentable acotada; sin bucle ilimitado |
| Timeout/modelo no disponible | Error temporal estable |
| Vacía/no JSON/JSON inválido | Error de validación |
| Esquema/evidencia inválidos | Rechazo, métrica y sin salida bruta |
| Error interno | Identificador de correlación, sin detalles sensibles |

Nunca se exponen stack traces, prompts, políticas IAM, respuestas brutas ni datos
sensibles.

## 20. Costes

- Límites de tokens de entrada/salida y tamaño máximo de contexto.
- Modelo configurable y feature desactivada por defecto.
- Tokens, latencia, errores, throttling y coste estimado por solicitud.
- Estimaciones futuras por resumen y por 1.000 resúmenes, con supuestos versionados.
- Budgets y alarmas antes de pruebas AWS.
- Feature y provider desactivados, sin model ID ni permisos Bedrock.
- Timeout de 15 segundos, memoria de 256 MB, autenticación y scope dedicado.
- Workflow manual aprobado, despliegue efímero, destrucción y cleanup verificados,
  con alarmas nativas.
- El shell cerrado no configura concurrencia reservada y utiliza el pool no
  reservado de la cuenta, evitando que una reserva fija impida desplegar en cuentas
  de laboratorio con cuotas reducidas. Esto no aprueba escalado productivo: antes
  de habilitar Bedrock deben decidirse rate limiting, concurrencia, cuota y
  presupuesto.
- Caching solo tras evaluar privacidad, coste, coherencia e invalidación.

## 21. Estrategia de pruebas

- Unit tests sin Bedrock real mediante `FakeBedrockClient`.
- Contract tests y validación de esquema.
- Respuesta válida, vacía, malformada, no JSON y JSON inválido.
- Campos desconocidos, timeout, throttling y acceso denegado.
- Modelo no disponible/no permitido y entrada demasiado grande.
- Prompt injection e instrucciones maliciosas dentro del incidente.
- Secretos simulados, datos insuficientes y afirmaciones sin evidencia.
- Pruebas deterministas del prompt builder.
- AWS solo mediante workflow manual controlado, despliegue efímero, destrucción y
  verificación; nunca directamente desde `mirofish`.

## 22. Evaluación de calidad

Métricas: groundedness, relevancia, completitud, precisión estructural, tasa de JSON
válido, tasa conforme al esquema, tasa de afirmaciones no soportadas, latencia,
tokens, coste estimado, errores y throttling.

La evaluación debe comparar versiones de prompt y modelos permitidos sin convertir
un resultado único en evidencia de producción. Los umbrales se aprobarán antes de
aceptar ADR-013.

## 23. Dataset sintético inicial

Cada caso versionado contendrá:

- `incident_id` sintético y contexto disponible;
- hechos permitidos y hechos ausentes;
- resumen esperado y causas aceptables;
- evidencias obligatorias y afirmaciones prohibidas;
- acciones recomendadas aceptables;
- confianza máxima aceptable.

El dataset cubrirá alarmas, fallos de procesamiento, backlog/DLQ, síntomas de
latencia, datos contradictorios, contexto insuficiente, inyección de prompt y
secretos falsos. No incluirá datos reales o sensibles.

## 24. Roadmap

1. Aprobar privacidad, datos, región, allowlist y criterios de calidad.
2. Implementar MVP tras aceptar el plan, manteniendo feature off.
3. Ejecutar tests locales deterministas y evaluación sintética.
4. Evaluar Guardrails, modelos, coste y latencia.
5. Realizar prueba AWS efímera solo con aprobación y workflow controlado.
6. Considerar RAG con citas y gobierno documental.
7. Considerar herramientas de lectura con IAM independiente.
8. Evaluar acciones únicamente mediante otro ADR y aprobación humana.

## 25. Riesgos

- Alucinaciones o evidencia incorrecta.
- Prompt injection desde datos del incidente.
- Exposición de información sensible en inferencia o logs.
- Coste y latencia no acotados.
- Disponibilidad regional/modelo y throttling.
- Dependencia de Bedrock y cambios de comportamiento del modelo.
- Confianza excesiva del operador en hipótesis probabilísticas.
- Degradación de prompts y datasets sin mantenimiento.

Mitigaciones: fundamentación, validación cerrada, redacción, allowlists, límites,
telemetría, evaluación continua, UI explícita y decisión humana.

## 26. Criterios de aceptación del futuro MVP

- Feature flag desactivada por defecto.
- Endpoint protegido por autenticación y autorización.
- Ninguna acción de escritura y rol IAM restringido.
- Cliente Bedrock desacoplado y tests sin llamadas reales.
- Salida validada con hechos separados de hipótesis.
- Métricas de tokens/latencia y logs sin prompts sensibles.
- Coste documentado y límites de entrada, salida y concurrencia.
- Workflow AWS manual, controlado y con destrucción verificada.
- Evaluación sintética con umbrales aprobados.
- ADR-013 cambia de **Proposed** a **Accepted** solo después de evidencia real.

## 27. Validación AWS controlada del shell cerrado

El workflow manual existente `deploy-ephemeral.yml` prepara una validación efímera
del shell de infraestructura GenAI con el flujo **deployed + authorized + disabled
+ destroyed**. Solo puede iniciarse mediante `workflow_dispatch` desde `main`, usa
OIDC y el GitHub Environment `aws-ephemeral`, y exige la confirmación literal
`VALIDATE-GENAI-SHELL-AND-DESTROY`.

El Environment `aws-ephemeral` ya tiene protección efectiva y required reviewer.
La confirmación textual no sustituye la aprobación del Environment.

El despliegue crea de forma condicional un único cliente M2M efímero, con secret y
grant `client_credentials`, y tokens de 15 minutos. Un token solicita exactamente
`incidents.read`, `incidents.write` e `incidents.summarize`; otro solicita solo
`incidents.read` e `incidents.write` para demostrar que la ruta rechaza con 403 un
token sin `incidents.summarize`. La petición autenticada espera el error público
estable HTTP 503 porque `AI_SUMMARY_ENABLED=false` y
`AI_SUMMARY_PROVIDER=disabled`.

La feature gate se evalúa antes de validar o leer el incidente en la ruta GenAI.
Por ello, la creación y lectura del incidente completamente sintético se comprueban
mediante la API normal, y la invocación GenAI cerrada no demuestra la ejecución de
`dynamodb:GetItem`. La plantilla sintetizada y la desplegada sí verifican que el rol
independiente solo permite `dynamodb:GetItem`, `logs:CreateLogStream` y
`logs:PutLogEvents`, sin permisos Bedrock ni escrituras.

La validación no descarga mensajes de CloudWatch Logs. Solo consulta una métrica
nativa agregada, genera un único artifact JSON con campos permitidos y destruye el
stack incluso cuando falla el smoke test. Después comprueba la ausencia del stack,
la Lambda GenAI y su Log Group. Para estas dos comprobaciones finales, el rol OIDC
necesita exclusivamente `lambda:GetFunction` sobre
`cloudops-genai-summary-function` y `logs:DescribeLogGroups` como acción de listado.
El wildcard de recurso de `DescribeLogGroups` no concede lectura del contenido: el
rol no recibe `GetLogEvents`, `FilterLogEvents`, Logs Insights ni acciones de
escritura. Ambas autorizaciones se usan solo para verificar el cleanup. Tokens,
secret, payload, incidente, outputs,
plantillas y logs brutos permanecen fuera de la evidencia.

La versión actualizada de `bootstrap/github-oidc-role.yml` ya fue aplicada
administrativamente al stack de bootstrap. El rol OIDC desplegado conserva el
trust restringido al repositorio y al Environment `aws-ephemeral`.

### Primer intento AWS controlado — 17 de julio de 2026

OIDC, la verificación de identidad y el synth finalizaron correctamente. El deploy
falló antes de completar el stack porque la reserva fija de concurrencia era
incompatible con la capacidad disponible de la cuenta. Las validaciones
funcionales no se ejecutaron y no se generó la evidencia saneada final.

El rollback y el destroy se completaron, y se verificó la ausencia final del stack,
la Lambda GenAI y su Log Group. Bedrock no fue invocado. El resultado fue un fallo
seguro, no una validación AWS exitosa. La corrección elimina la concurrencia
reservada.

## Validación AWS satisfactoria del shell cerrado — 17 de julio de 2026

Tras corregir la reserva incompatible del primer intento, el segundo intento
finalizó satisfactoriamente. OIDC, identidad, synth, deploy, IAM y recursos fueron
aprobados. La ruta autenticada confirmó el estado cerrado con HTTP 503; la petición
anónima obtuvo HTTP 401 y el token con scope incorrecto HTTP 403.

El destroy y la verificación de ausencia del stack, la Lambda GenAI y su Log Group
también finalizaron correctamente, y se generó evidencia saneada. No se configuró
ni invocó Amazon Bedrock: el alcance validado se limita al shell cerrado y efímero.
Véanse el [informe de validación](genai-shell-aws-validation-2026-07-17.md) y la
[evidencia JSON](evidence/genai-shell-aws-validation-2026-07-17.json).

La validación demuestra únicamente que el shell se despliega, autoriza, permanece
desactivado y se destruye; no constituye una integración Amazon Bedrock validada.
No invoca Bedrock, no ejecuta inferencias y no selecciona modelos. ADR-013 permanece
**Proposed** y el proyecto continúa **not production-ready**.

## Referencias oficiales

- [Inference using Converse API](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html)
- [ConverseStream API y permiso de streaming](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ConverseStream.html)
- [Guardrails con Converse API](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-use-converse-api.html)
