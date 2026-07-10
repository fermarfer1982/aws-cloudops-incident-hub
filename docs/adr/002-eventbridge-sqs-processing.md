# ADR-002: EventBridge y SQS para procesamiento asíncrono

## Estado

Aceptado.

## Contexto

La ingesta y el procesamiento estaban acoplados en una única petición HTTP. Un fallo en clasificación o persistencia afectaba directamente al cliente y no existía un mecanismo explícito para absorber picos o aislar mensajes problemáticos.

## Decisión

Utilizar un bus personalizado de EventBridge para recibir eventos validados, una regla para enrutar incidencias a una cola SQS estándar y una Lambda independiente como consumidor. La cola tendrá una DLQ con `maxReceiveCount=3` y el event source mapping utilizará respuestas parciales de lote.

El modo Docker mantendrá un adaptador síncrono para evitar introducir una plataforma de emulación adicional en el laboratorio local.

## Consecuencias

### Positivas

- Desacoplamiento entre disponibilidad de la API y procesamiento.
- Absorción de picos mediante buffering.
- Reintentos automáticos y aislamiento en DLQ.
- Posibilidad de añadir nuevos consumidores a EventBridge.
- Idempotencia explícita ante entrega duplicada.

### Negativas

- Consistencia eventual en AWS.
- Mayor número de componentes y métricas operativas.
- El cliente recibe aceptación, no el resultado final del procesamiento.
- La ruta local y la ruta AWS no son idénticas, por lo que ambas requieren pruebas.
