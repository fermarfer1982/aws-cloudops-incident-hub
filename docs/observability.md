# Observabilidad operativa

## Objetivo

La solución define observabilidad como código sin emitir métricas personalizadas. El dashboard y las alarmas utilizan métricas nativas de Lambda y SQS, lo que mantiene el diseño sencillo, auditable y fácil de retirar junto con el stack.

La infraestructura no se despliega de forma permanente. El laboratorio local y la demo de GitHub Pages siguen funcionando sin consumir servicios de AWS.

## Dashboard

Nombre: `cloudops-incident-hub-operations`

El dashboard presenta:

- Errores y throttling de la Lambda de ingesta.
- Errores y throttling de la Lambda procesadora.
- Duración p95 de ambas funciones.
- Mensajes visibles en la cola de procesamiento.
- Antigüedad del mensaje más antiguo.
- Mensajes visibles en la Dead Letter Queue.
- Estado de las cuatro alarmas operativas.

La ventana inicial es de tres horas para facilitar una demostración breve después de un despliegue efímero.

## Alarmas

| Alarma | Señal | Umbral | Interpretación |
|---|---|---:|---|
| `cloudops-api-function-errors` | Errores Lambda API | >= 1 en 5 min | La ingesta no pudo aceptar o consultar eventos correctamente |
| `cloudops-processor-function-errors` | Errores Lambda processor | >= 1 en 5 min | El consumidor SQS devolvió un error de ejecución |
| `cloudops-processing-queue-age` | Edad del mensaje más antiguo | >= 300 s durante 10 min | El procesamiento no mantiene el ritmo de llegada |
| `cloudops-processing-dlq-messages` | Mensajes visibles en DLQ | >= 1 | Existe al menos un evento que requiere intervención |

Todas las alarmas utilizan `notBreaching` cuando no existen datos. El perfil predeterminado no configura acciones de notificación. El perfil ChatOps opcional crea un tópico SNS, conecta las transiciones `ALARM` y `OK` y entrega las notificaciones mediante Amazon Q Developer a un canal autorizado de Slack.

## Perfil ChatOps opcional

La integración con Slack está desactivada por defecto.

Para activarla deben proporcionarse juntos `slack_workspace_id` y `slack_channel_id`. Los identificadores reales se suministran durante el despliegue y no se versionan en el repositorio.

El perfil crea un tópico SNS, conecta las cuatro alarmas en estados `ALARM` y `OK`, configura Amazon Q para Slack y aplica una política IAM de mínimo privilegio. El logging de Amazon Q permanece desactivado.

La infraestructura está validada mediante tests y síntesis local. La entrega real en Slack continúa pendiente de una prueba AWS controlada.

## Principios de diseño

### Métricas nativas antes que métricas personalizadas

Las métricas nativas permiten observar disponibilidad, latencia, capacidad y acumulación de trabajo sin introducir llamadas `PutMetricData` ni una dependencia adicional en el código.

### Señales accionables

No se genera una alarma por cada métrica disponible. Cada alarma está asociada a una actuación concreta:

- Errores de API: revisar logs de la función de ingesta y el estado de DynamoDB o EventBridge.
- Errores del procesador: revisar el fallo del lote y los mensajes reintentados.
- Edad de cola: comprobar throttling, concurrencia reservada y duración del procesador.
- DLQ: ejecutar el runbook de análisis y redrive.

### Retención limitada

Los grupos de logs se conservan un día y se eliminan con el stack. Esta configuración es apropiada para el laboratorio, pero no para una plataforma de producción con requisitos de auditoría.

## Validación como código

Los tests de CDK comprueban:

- Existencia de un dashboard.
- Existencia de cuatro alarmas.
- Nombres estables de alarmas.
- Tratamiento de ausencia de datos como `notBreaching`.
- Ausencia de acciones automáticas de alarma.
- Eliminación del dashboard con el stack.

## Evolución para producción

Una versión empresarial debería añadir:

- Suscripciones SNS y escalado de avisos.
- Logs centralizados en una cuenta de seguridad o log archive.
- Retención acorde con requisitos legales.
- Trazabilidad distribuida cuando el volumen y la criticidad lo justifiquen.
- Métricas de negocio, por ejemplo eventos aceptados, duplicados descartados y tiempo total de procesamiento.
- SLO, objetivos de disponibilidad y presupuestos de error.
- Dashboards diferenciados para operación, seguridad y dirección técnica.

## Consideración de costes

El repositorio solo sintetiza estos recursos. No se mantiene un despliegue activo en AWS. Un despliegue real debe revisarse con AWS Pricing Calculator y eliminarse al finalizar la demostración; un dashboard y varias alarmas pueden generar consumo facturable según la cuenta y el uso.
