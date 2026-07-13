# ADR-012: Amazon Q y Slack para ChatOps operativo

## Estado

Aceptado y validado para la arquitectura de referencia mediante una prueba AWS controlada con entrega real en Slack.

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
- La entrega real `ALARM` y `OK` fue validada el 13 de julio de 2026 mediante el workflow `29234347159`.
- Este cambio no convierte el workload en production-ready.

## Evidencia de validación

WA-014 se validó mediante el workflow efímero `29234347159`.

La prueba confirmó:

1. Despliegue de un tópico SNS.
2. Despliegue de una configuración Amazon Q para Slack.
3. Existencia de cuatro alarmas de CloudWatch.
4. Transición controlada de `OK` a `ALARM`.
5. Entrega de la alarma en Slack.
6. Transición controlada de `ALARM` a `OK`.
7. Entrega de la recuperación en Slack.
8. Destrucción y eliminación verificadas del stack efímero.

La evidencia técnica y visual está documentada en
[`wa-014-chatops-evidence-2026-07-13.md`](../wa-014-chatops-evidence-2026-07-13.md).
