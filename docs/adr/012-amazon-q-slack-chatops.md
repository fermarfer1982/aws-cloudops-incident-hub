# ADR-012: Amazon Q y Slack para ChatOps operativo

## Estado

Aceptado para la arquitectura de referencia. La entrega real de alarmas sigue pendiente de validación.

## Contexto

La solución dispone de cuatro alarmas de CloudWatch y routing opcional mediante SNS. WA-014 exige demostrar que una alarma llega a un receptor autorizado.

## Decisión

Se implementa un perfil ChatOps opcional con este flujo:

CloudWatch Alarm -> SNS -> Amazon Q Developer -> Slack

La configuración requiere `slack_workspace_id` y `slack_channel_id`. Ambos valores deben proporcionarse juntos y no se almacenan en el repositorio.

Las cuatro alarmas publican transiciones `ALARM` y `OK` en SNS.

La configuración utiliza:

- `LoggingLevel.NONE`
- `user_role_required=False`
- Política IAM propia de mínimo privilegio
- Lectura de CloudWatch
- Consulta de metadatos SNS
- Ningún permiso administrativo

El perfil predeterminado continúa sin SNS y sin Amazon Q.

## Consecuencias

- Se demuestra integración entre CloudWatch, SNS, IAM, Amazon Q y Slack.
- No se utiliza `AdministratorAccess`.
- Los recursos se eliminan junto con el stack.
- La autorización inicial del workspace es manual.
- La prueba AWS controlada de entrega real sigue pendiente.
- Este cambio no convierte el workload en production-ready.

## Evidencia pendiente

Antes de cerrar WA-014 se debe conservar evidencia saneada de:

1. Despliegue controlado.
2. Transición a `ALARM`.
3. Recepción en Slack.
4. Transición a `OK`.
5. Recepción de la recuperación.
6. Destrucción verificada del stack.
