# ADR-003: observabilidad con métricas nativas de CloudWatch

- Estado: Aceptada
- Fecha: 2026-07-10

## Contexto

La arquitectura necesita demostrar capacidad operativa sin convertir el laboratorio en una plataforma costosa o excesivamente compleja. Lambda y SQS ya publican métricas operativas que permiten detectar errores, throttling, latencia y acumulación de mensajes.

## Decisión

Se utilizarán métricas nativas de AWS para construir:

- Un dashboard de CloudWatch.
- Alarmas de errores de las dos funciones Lambda.
- Una alarma de antigüedad de mensajes en la cola principal.
- Una alarma de mensajes visibles en la DLQ.

No se emitirán métricas personalizadas en esta fase y no se configurarán acciones SNS automáticamente.

## Consecuencias positivas

- No se modifica el código de negocio para publicar telemetría.
- La infraestructura completa permanece declarada en CDK.
- Las alarmas tienen una respuesta operacional documentada.
- El stack puede desplegarse y destruirse de forma reproducible.
- Se reduce el ruido evitando alarmas sin una actuación definida.

## Consecuencias negativas

- No existen métricas de negocio como eventos aceptados, descartados o duplicados.
- No se envían notificaciones mientras no se conecte una acción de alarma.
- Las métricas de servicio no ofrecen por sí solas trazabilidad extremo a extremo.
- Un despliegue real de dashboard y alarmas debe incluirse en la estimación de costes.

## Alternativas descartadas

### Métricas personalizadas desde las Lambdas

Aportan mayor detalle funcional, pero introducen llamadas adicionales, coste potencial y acoplamiento entre lógica de negocio y observabilidad.

### AWS X-Ray en todas las funciones

Es útil para trazabilidad distribuida, pero no es necesario para demostrar el flujo básico del laboratorio y añadiría complejidad operacional.

### Plataforma externa de observabilidad

Datadog, Grafana Cloud u otras soluciones son válidas en producción, pero ocultarían parte del conocimiento nativo de AWS que este proyecto pretende demostrar.
