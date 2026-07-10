# Control de coste

El repositorio está diseñado para ejecutarse completamente en local y publicarse como demo estática en GitHub Pages.

## Guardrails técnicos

- La plantilla CDK no crea NAT Gateway, EC2, RDS, ALB, EKS, OpenSearch ni ElastiCache.
- DynamoDB utiliza `PAY_PER_REQUEST` y `RemovalPolicy.DESTROY`.
- Lambda limita la concurrencia reservada a 2, usa 256 MB y timeout de 10 segundos.
- Los logs tienen retención de un día.
- No se crea dominio, zona Route 53, WAF, VPC ni endpoint privado.
- El despliegue cloud no forma parte del pipeline automático de cada push.

## Importante

El validador del repositorio reduce el riesgo, pero AWS Budgets y las alertas de facturación no son bloqueos de gasto en tiempo real. La ejecución local y GitHub Pages son los únicos modos que garantizan no consumir servicios facturables de AWS.
