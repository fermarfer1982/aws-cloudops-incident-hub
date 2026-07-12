# Well-Architected remediation backlog

Este backlog convierte los hallazgos de `docs/well-architected-review.md` en acciones priorizadas. No implica que el laboratorio vaya a implementar todos los controles de producción; separa con claridad lo que ya está cubierto, lo que se acepta por el alcance de laboratorio y lo que bloquearía un uso real.

## Criterios de prioridad

| Prioridad | Criterio |
|---|---|
| P0 | Bloquea cualquier exposición a usuarios o datos reales. |
| P1 | Debe resolverse antes de considerar el workload production-ready. |
| P2 | Mejora relevante para operación, escalabilidad o gobierno. |
| P3 | Optimización posterior o dependiente de requisitos todavía no definidos. |

## Backlog priorizado

| ID | Prioridad | Pilar | Acción | Resultado verificable | Dependencias | Estado |
|---|---:|---|---|---|---|---|
| WA-001 | P0 | Security | Añadir autenticación a API Gateway | Todas las rutas excepto `/health` rechazan peticiones anónimas | Amazon Cognito y JWT authorizer | Completado en referencia |
| WA-002 | P0 | Security | Implementar autorización por operaciones | Scopes separados para crear, leer y gestionar incidencias | WA-001 | Completado en referencia |
| WA-003 | P0 | Security | Sustituir CORS `*` por allowlist | CloudFormation contiene únicamente orígenes aprobados | Dominios configurables mediante contexto CDK | Completado en referencia |
| WA-004 | P0 | Performance | Eliminar DynamoDB Scan del listado principal | Consultas usan Query y un patrón de claves documentado | Cuatro GSIs de acceso | Completado en referencia |
| WA-005 | P0 | Performance | Eliminar agregación síncrona por Scan en `/metrics` | Métricas proceden de agregados incrementales o materializados | Tabla de métricas transaccional | Completado en referencia |
| WA-006 | P1 | Reliability | Definir RTO y RPO | Documento aprobado con valores, responsables y supuestos | Requisitos de negocio | Definido en referencia; pendiente aprobación |
| WA-007 | P1 | Reliability | Activar PITR para entornos persistentes | Test CDK verifica `PointInTimeRecoverySpecification` | WA-006 | Completado en referencia |
| WA-008 | P1 | Reliability | Crear y probar restauración | Runbook y evidencia de un restore exitoso | WA-007 | Runbook completado; restore real pendiente |
| WA-009 | P1 | Operational excellence | Definir SLO y error budget | SLO de disponibilidad, latencia y procesamiento asíncrono | Datos de carga y negocio | Baselines local y AWS registrados; objetivos y aprobación pendientes |
| WA-010 | P1 | Operational excellence | Asignar ownership | Matriz RACI o tabla con owner técnico, seguridad, coste y operación | Organización objetivo | Completado para repositorio y laboratorio; roles organizativos de producción pendientes |
| WA-011 | P1 | Cost optimization | Configurar AWS Budget y anomalías de coste | Evidencia de presupuesto, umbrales y receptores | Cuenta AWS de laboratorio | Completado para laboratorio: dos budgets, notificaciones y dos suscripciones de anomalías evidenciadas; gobierno financiero de producción pendiente |
| WA-012 | P1 | Security | Añadir throttling y protección frente a abuso | Límites explícitos en API Gateway; WAF evaluado si aplica | Perfil de tráfico | Throttling y baseline AWS conservador validados; decisión WAF y carga límite pendientes |
| WA-013 | P1 | Security | Añadir análisis de dependencias y secretos | Dependabot/CodeQL/secret scanning o herramienta equivalente | Política GitHub | Automatización completada; configuración y alertas reales pendientes |
| WA-014 | P1 | Operational excellence | Enrutar alarmas a un canal real | Una alarma de prueba llega a un receptor autorizado | SNS y Amazon Q Developer para Slack | IaC ChatOps opt-in completada y validada; receptor real y evidencia ALARM/OK pendientes |
| WA-015 | P1 | Reliability | Documentar estrategia regional | Decisión explícita: single-region recovery o multi-region | WA-006 | Single-region documentado; decisión regional pendiente |
| WA-016 | P2 | Performance | Implementar paginación con continuation token | `GET /events` recupera páginas acotadas mediante cursor y sin Scan | WA-004 | Completado y validado localmente con 365 IDs únicos y 0 duplicados |
| WA-017 | P2 | Performance | Ejecutar pruebas de carga | Informe con p50, p95, errores, throttles, backlog y coste estimado | Tráfico representativo | Completado: baseline local y AWS efímero validado; 152 solicitudes, 0% errores y limpieza verificada |
| WA-018 | P2 | Performance | Ajustar memoria, concurrencia y batch | Parámetros sustentados por mediciones y comparativa | WA-017 | Baseline AWS justifica mantener parámetros actuales; comparativa controlada pendiente si aumenta el objetivo de escala |
| WA-019 | P2 | Operational excellence | Ejecutar game day | Evidencia de fallo Lambda, backlog, DLQ y recuperación | WA-014 | Pendiente |
| WA-020 | P2 | Operational excellence | Añadir runbook de release y rollback | Criterios de rollback y pasos comprobables | Estrategia de release | Pendiente |
| WA-021 | P2 | Security | Definir clasificación y retención de datos | Tabla de categorías, retención, cifrado y borrado | Requisitos legales | Pendiente |
| WA-022 | P2 | Security | Generar SBOM | Artifact o release incluye SBOM verificable | Herramienta seleccionada | Workflow completado; artifact real pendiente de ejecución |
| WA-023 | P2 | Cost optimization | Medir coste por 1.000 incidencias | Estimación low/expected/peak con supuestos versionados | WA-017 | Telemetría AWS disponible; facturación final y coste unitario pendientes |
| WA-024 | P2 | Cost optimization | Ampliar tags obligatorios | Owner, application, environment, cost-center y expiration | Convención de tagging | Pendiente |
| WA-025 | P2 | Sustainability | Definir KPI de eficiencia | Incidencias por invocación y GB-second, retención y tendencia | WA-017 | Telemetría AWS disponible; definición y seguimiento del KPI pendientes |
| WA-026 | P2 | Sustainability | Revisar retención por valor de negocio | Política aplicada a tabla, logs, artifacts y DLQ | WA-021 | Pendiente |
| WA-027 | P3 | Reliability | Probar fallo regional | Evidencia de recuperación en región alternativa si se requiere | WA-015 | Pendiente |
| WA-028 | P3 | Security | Diseñar cuenta central de seguridad | CloudTrail, GuardDuty, Security Hub y agregación organizativa | Arquitectura multi-account | Pendiente |
| WA-029 | P3 | Cost optimization | Inventariar recursos huérfanos | Automatización o consulta periódica fuera del stack | Uso recurrente del laboratorio | Pendiente |
| WA-030 | P3 | Sustainability | Evaluar región con criterios múltiples | Decisión que combine latencia, regulación, resiliencia y sostenibilidad | Requisitos de negocio | Pendiente |

## Riesgos aceptados en el laboratorio

Estos riesgos no deben confundirse con controles de producción completados:

- El modo Docker local permanece sin autenticación cloud dentro de una red de laboratorio confiable.
- El perfil efímero elimina las tablas al destruir el stack.
- El perfil efímero no habilita PITR ni backup persistente.
- Las alarmas no tienen acciones de notificación salvo que se configure un receptor explícito.
- Los logs del perfil efímero tienen retención de un día.
- El event source mapping limita la concurrencia SQS a dos en el laboratorio.
- El throttling se validó de forma conservadora a 5 requests/s, pero no se ha probado el límite de capacidad.
- GitHub push protection y otras opciones de seguridad requieren evidencia de configuración del repositorio.
- Los baselines local y AWS pasan los umbrales provisionales; la prueba AWS es corta y no representa capacidad sostenida.
- El workflow AWS produjo una ejecución aprobada, artifact saneado y limpieza verificada el 2026-07-12.

Los controles P0 se consideran completados en la implementación de referencia. Los controles P1 de recuperación, operación y seguridad disponen de IaC, automatización o documentación parcial, pero requieren aprobación, despliegue y evidencia real antes de aceptar usuarios o datos reales.

## Definition of done para producción

El workload no debe describirse como production-ready hasta que, como mínimo:

1. WA-001 a WA-015 estén cerrados o exista una aceptación de riesgo formal con owner y fecha de expiración.
2. Existan SLO, RTO, RPO y ownership aprobados.
3. Se haya probado restore, rollback y respuesta ante mensajes en DLQ.
4. La API tenga autenticación, autorización, CORS restringido y límites de abuso validados en el entorno objetivo.
5. No existan scans completos en rutas operativas principales y se haya probado paginación con carga representativa.
6. Se hayan configurado controles de coste de cuenta.
7. CodeQL, Dependabot, secret scanning y SBOM produzcan evidencia real y tengan un proceso de triage.
8. El baseline AWS justifique memoria, concurrencia, batch y throttling.
9. La revisión Well-Architected se repita con evidencias de un entorno real.

## Cadencia de revisión

Revisar este backlog:

- En cada cambio arquitectónico relevante.
- Antes de cualquier despliegue persistente.
- Después de un incidente o game day.
- Como máximo cada seis meses.
