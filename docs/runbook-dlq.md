# Runbook: mensajes en la Dead Letter Queue

## Alcance

Este procedimiento describe cómo investigar eventos que han agotado los reintentos de la cola `cloudops-incident-processing` y han terminado en `cloudops-incident-processing-dlq`.

## Condición de entrada

La alarma `cloudops-processing-dlq-messages` cambia a estado `ALARM` cuando existe al menos un mensaje visible en la DLQ.

## Objetivo operacional

- Identificar la causa del fallo.
- Evitar la pérdida o duplicación de incidencias.
- Corregir el problema antes de reintroducir mensajes.
- Mantener evidencia de la intervención.

## Procedimiento

### 1. Confirmar el alcance

Revisar en CloudWatch:

- Número de mensajes visibles en la DLQ.
- Errores de la Lambda procesadora.
- Edad del mensaje más antiguo en la cola principal.
- Throttling y duración de la Lambda procesadora.

Determinar si se trata de un único evento mal formado o de un fallo sistémico.

### 2. Revisar los logs

Abrir el grupo de logs de la Lambda procesadora y buscar:

- `messageId` del registro SQS.
- `event_id` del evento de negocio.
- Excepciones de validación.
- Errores de acceso a DynamoDB.
- Timeouts o throttling.

No copiar secretos ni datos sensibles en tickets o capturas.

### 3. Inspeccionar el mensaje sin eliminarlo

Recibir un mensaje de la DLQ con visibilidad temporal y conservar:

- Message ID.
- ApproximateReceiveCount.
- Cuerpo completo del sobre EventBridge.
- `detail.event_id`.
- Fecha y hora de recepción.

No reenviar mensajes hasta entender la causa.

### 4. Clasificar el fallo

| Categoría | Ejemplo | Actuación |
|---|---|---|
| Evento inválido | Campo requerido ausente | Corregir el productor o descartar con evidencia |
| Fallo transitorio | Error temporal de AWS | Confirmar recuperación y redrive controlado |
| Defecto de código | Excepción reproducible | Corregir, probar y desplegar antes del redrive |
| Permisos | Acceso denegado a DynamoDB | Corregir IAM con mínimo privilegio |
| Capacidad | Throttling o backlog creciente | Revisar concurrencia, batch size y duración |

### 5. Verificar idempotencia

Antes de reintroducir el mensaje, consultar DynamoDB por el `incident_id` determinista.

- Si la incidencia ya existe, no es necesario reprocesarla.
- Si no existe, el redrive es seguro siempre que el defecto esté corregido.
- La escritura condicional protege frente a entregas repetidas, pero no sustituye la revisión operacional.

### 6. Corregir y validar

Ejecutar antes del redrive:

```bash
ruff check backend tests infrastructure scripts
pytest -q tests
cd infrastructure && PYTHONPATH=. python -m pytest -q tests
cd ..
```

Para reproducir localmente el contrato SQS:

```bash
make simulate-async
```

### 7. Redrive controlado

Mover primero un único mensaje a la cola principal y comprobar:

- La Lambda lo procesa sin error.
- La incidencia aparece en DynamoDB.
- No se genera un duplicado.
- El contador de la DLQ disminuye.

Solo después redirigir el resto de mensajes.

### 8. Cierre

Registrar:

- Causa raíz.
- Número de mensajes afectados.
- Cambio aplicado.
- Evidencia de tests.
- Resultado del redrive.
- Acción preventiva.

La alarma volverá a `OK` cuando no queden mensajes visibles en la DLQ.

## No hacer

- No purgar la DLQ como primera medida.
- No reenviar todos los mensajes sin probar uno primero.
- No ampliar permisos IAM con comodines para resolver rápidamente un acceso denegado.
- No aumentar reintentos indefinidamente para ocultar un defecto determinista.
- No borrar logs antes de capturar la evidencia necesaria.
