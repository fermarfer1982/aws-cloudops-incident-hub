# Procesamiento dirigido por eventos

## Objetivo

Separar la recepción de una incidencia de su procesamiento para absorber picos, limitar el impacto de fallos transitorios y permitir que cada componente escale de forma independiente.

## Flujo en AWS

1. API Gateway invoca la Lambda de ingesta.
2. FastAPI valida el contrato y genera `event_id` e `incident_id`.
3. La Lambda publica `InfrastructureIncidentReceived` en un bus personalizado de EventBridge.
4. Una regla filtra por `source` y `detail-type` y entrega el evento a SQS.
5. La Lambda de procesamiento consume lotes de hasta diez mensajes.
6. Cada mensaje se valida, se clasifica y se persiste en DynamoDB.
7. Tras tres recepciones fallidas, SQS mueve el mensaje a la Dead Letter Queue.

## Idempotencia

SQS y EventBridge ofrecen entrega al menos una vez, por lo que un mismo evento puede llegar más de una vez. El sistema evita duplicados con dos mecanismos:

- `incident_id` se deriva de la fecha del evento y de `event_id`.
- DynamoDB utiliza una escritura condicional con `attribute_not_exists(incident_id)`.

Si el evento ya fue procesado, la Lambda recupera el registro existente y finaliza correctamente.

## Errores parciales de lote

El event source mapping activa `ReportBatchItemFailures`. El procesador captura errores por mensaje y devuelve únicamente los `messageId` fallidos. Los mensajes procesados correctamente no vuelven a la cola aunque otro elemento del mismo lote falle.

## Límites operativos del laboratorio

- Concurrencia reservada: 2 para cada Lambda.
- Memoria: 256 MB.
- Timeout de API: 10 segundos.
- Timeout del procesador: 15 segundos.
- Visibility timeout de SQS: 60 segundos.
- Retención de la cola principal: 1 día.
- Retención de la DLQ: 14 días.
- Logs: 1 día.

## Ejecución local

El modo local no intenta emular EventBridge ni SQS. Cuando `EVENT_BUS_NAME` no está definido, el servicio usa un adaptador síncrono y persiste directamente en DynamoDB Local. Así se conserva una experiencia de desarrollo reproducible y sin dependencias cloud, mientras que CDK y los tests validan la topología AWS.

## Pruebas cubiertas

- Contrato de publicación en EventBridge.
- Respuesta `202 Accepted` en modo asíncrono.
- Procesamiento correcto de mensajes SQS.
- Respuesta parcial ante mensajes malformados.
- Existencia de EventBridge, SQS, DLQ, Lambda y event source mapping en CloudFormation.
- Cifrado administrado, redrive policy, retención y límites de cómputo.
- Ausencia de NAT Gateway, EC2, RDS, ALB, EKS y OpenSearch.
