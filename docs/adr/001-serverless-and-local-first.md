# ADR-001: arquitectura serverless y desarrollo local-first

## Estado

Aceptado.

## Contexto

El proyecto debe demostrar arquitectura AWS sin mantener infraestructura cloud activa ni generar costes.

## Decisión

La aplicación se diseña para API Gateway, Lambda y DynamoDB, pero se ejecuta en local mediante Docker, FastAPI y DynamoDB Local. El frontend público opera con datos demo en GitHub Pages.

## Consecuencias

- El proyecto es reproducible y demostrable sin una cuenta AWS activa.
- CDK permite validar la arquitectura cloud mediante síntesis y tests.
- Algunas diferencias de comportamiento entre DynamoDB Local y el servicio administrado deben cubrirse con pruebas de integración temporales antes de producción.
