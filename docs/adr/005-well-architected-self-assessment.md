# ADR-005: Revisión Well-Architected basada en evidencias del repositorio

- **Estado:** Aceptado
- **Fecha:** 2026-07-10

## Contexto

AWS CloudOps Incident Hub es un laboratorio de portfolio con una arquitectura local operativa y una arquitectura AWS definida mediante CDK. El repositorio ya contiene pruebas, workflows, guardrails, observabilidad, runbooks y decisiones arquitectónicas.

Era necesario evaluar el diseño con un marco coherente sin presentar el resultado como una auditoría externa ni como una certificación de producción. También era necesario separar claramente:

- Controles ya implementados.
- Riesgos aceptables únicamente en un laboratorio efímero.
- Bloqueadores para un uso con usuarios o datos reales.
- Mejoras que dependen de requisitos de negocio todavía inexistentes.

## Decisión

Se mantendrá una autoevaluación versionada contra los seis pilares del AWS Well-Architected Framework:

1. Excelencia operativa.
2. Seguridad.
3. Fiabilidad.
4. Eficiencia del rendimiento.
5. Optimización de costes.
6. Sostenibilidad.

La revisión se fundamentará exclusivamente en evidencias presentes en el repositorio y utilizará una escala cualitativa de riesgo. No se asignará una puntuación numérica agregada, porque podría transmitir una precisión no respaldada por requisitos, tráfico real o una revisión en AWS Well-Architected Tool.

Los hallazgos se convertirán en un backlog separado con prioridad, dependencias, estado y resultado verificable. La CI comprobará que el documento conserva los seis pilares, los metadatos mínimos y los principales bloqueadores de producción.

## Consecuencias positivas

- La madurez y las limitaciones del proyecto quedan explícitas.
- Los riesgos del laboratorio no se presentan como buenas prácticas de producción.
- Las decisiones futuras pueden rastrearse hasta hallazgos concretos.
- El repositorio demuestra criterio arquitectónico, no solo capacidad de implementación.
- La revisión puede repetirse y compararse después de cambios relevantes.

## Consecuencias negativas

- La revisión requiere mantenimiento cuando cambia la arquitectura.
- Parte del backlog no puede cerrarse sin requisitos reales de negocio.
- La CI valida estructura y trazabilidad documental, no garantiza que las conclusiones sean correctas.
- La autoevaluación no sustituye una revisión externa ni el uso formal de AWS Well-Architected Tool.

## Alternativas consideradas

### Usar únicamente AWS Well-Architected Tool

Descartado para esta fase porque requeriría trabajar sobre una cuenta AWS y no aporta valor suficiente al modo local de coste cero. Podrá utilizarse cuando exista un entorno persistente o una revisión formal.

### Publicar una puntuación global

Descartado porque una cifra única ocultaría diferencias importantes entre el laboratorio y un entorno de producción.

### No documentar riesgos aceptados

Descartado porque podría inducir a interpretar CORS abierto, API anónima, ausencia de PITR o consultas Scan como decisiones aptas para producción.

## Criterios de revisión futura

Este ADR se revisará cuando:

- Se utilice AWS Well-Architected Tool.
- Existan usuarios o datos reales.
- Se definan SLO, RTO y RPO.
- Se introduzca autenticación.
- Se diseñe la arquitectura multi-account.
- Cambie el marco de evaluación utilizado.