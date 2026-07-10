# ADR-007: Cognito, scopes JWT y patrones DynamoDB Query

- **Estado:** Aceptado
- **Fecha:** 2026-07-10

## Contexto

La revisión Well-Architected identificó cinco bloqueadores P0 en la implementación AWS de referencia:

1. API sin autenticación.
2. Ausencia de autorización por operación.
3. CORS comodín.
4. Listado de incidencias mediante DynamoDB Scan.
5. Métricas calculadas mediante un Scan y agregación síncrona.

El proyecto debe seguir funcionando en Docker local sin requerir servicios AWS ni credenciales de usuarios cloud.

## Decisión

### Identidad y autorización

La API HTTP desplegada en AWS utilizará Amazon Cognito como emisor OAuth 2.0/OpenID Connect y un authorizer JWT de API Gateway. Se definen tres scopes:

- `cloudops-incident-hub/incidents.read`.
- `cloudops-incident-hub/incidents.write`.
- `cloudops-incident-hub/incidents.manage`.

`GET /health` será público. Las demás rutas exigirán token y scope en API Gateway antes de invocar Lambda. El cliente de navegador utilizará authorization code y no almacenará un client secret.

El modo Docker local permanece sin Cognito ni API Gateway y se considera únicamente un laboratorio de desarrollo en una red confiable.

### CORS

API Gateway, Lambda, FastAPI y Docker utilizarán allowlists explícitas. Los orígenes y callback URLs podrán sobrescribirse mediante contexto CDK. El carácter comodín no será un valor válido en la infraestructura de referencia.

### Acceso a incidencias

La tabla mantendrá `incident_id` como clave primaria y añadirá GSIs por tiempo, sitio, estado y severidad. Los listados utilizarán DynamoDB Query con orden descendente por `created_at`; no se permitirá `dynamodb:Scan` en IAM.

### Métricas

Una tabla separada almacenará contadores globales y por sitio. La creación de una incidencia actualizará incidencia y contadores mediante `TransactWriteItems`. Los cambios de estado actualizarán los contadores de estado dentro de otra transacción con control optimista.

## Consecuencias positivas

- Las rutas de datos quedan protegidas por identidad y scopes.
- El backend Lambda no procesa peticiones anónimas rechazadas por API Gateway.
- Los accesos operativos dejan de recorrer la tabla completa.
- Las métricas tienen coste proporcional a las escrituras y al número de sitios, no al número total de incidencias.
- La entrega duplicada de SQS no incrementa contadores dos veces.
- La CI puede detectar regresiones en autorización, CORS y uso de Scan.

## Consecuencias negativas

- Cognito, el dominio alojado y el flujo OAuth añaden componentes que deben operarse y probarse.
- Los GSIs aumentan el coste y la amplificación de escritura.
- Los contadores materializados exigen transacciones y una estrategia de reconciliación ante cambios manuales externos.
- El listado combinado por varios filtros puede aplicar filtros secundarios sobre una partición ya acotada.
- La API todavía necesita paginación mediante continuation token.

## Alternativas consideradas

### API keys

Descartadas como mecanismo principal porque identifican consumidores y permiten cuotas, pero no resuelven identidad de usuario ni autorización granular.

### Autorización dentro de FastAPI

Descartada como único control. La autorización de borde evita invocar Lambda para solicitudes sin token o scope válido. El backend podrá añadir controles de dominio adicionales cuando existan requisitos de negocio.

### Mantener una tabla y calcular métricas bajo demanda

Descartado porque perpetuaría el coste lineal y la latencia creciente del Scan.

### DynamoDB Streams para métricas

Válido para cargas mayores, pero innecesario en esta fase. Las transacciones ofrecen consistencia inmediata y un diseño más pequeño para el laboratorio.

## Criterios de revisión futura

Revisar esta decisión cuando se introduzcan clientes máquina-a-máquina, un IdP empresarial, autorización por tenant, paginación, cargas que generen particiones calientes o requisitos de reconciliación y auditoría de métricas.
