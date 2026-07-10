# Arquitectura

## MVP ejecutable

```mermaid
flowchart LR
    U[Agente o simulador] --> A[FastAPI local / API Gateway HTTP API]
    A --> L[Aplicación Python compatible con Lambda]
    L --> D[(DynamoDB Local / Amazon DynamoDB)]
    G[GitHub Actions] --> T[Tests + CDK synth + cost guardrail]
    P[GitHub Pages] --> F[Dashboard estático en modo demo]
```

El código de negocio no depende del modo de ejecución. En local, Uvicorn sirve FastAPI dentro de Docker. En AWS, Mangum adapta el evento de API Gateway al mismo objeto ASGI.

## Fase 2

```mermaid
flowchart LR
    API[API Gateway] --> ING[Lambda Ingestion]
    ING --> EB[EventBridge]
    EB --> Q[SQS]
    Q --> PROC[Lambda Processor]
    Q --> DLQ[Dead Letter Queue]
    PROC --> DB[(DynamoDB)]
    PROC --> SNS[SNS notifications]
```

La fase 2 añadirá procesamiento asíncrono, reintentos, idempotencia y recuperación mediante DLQ.
