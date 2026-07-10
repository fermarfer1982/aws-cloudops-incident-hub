# ADR-004: GitHub OIDC para despliegues efímeros

- Estado: aceptado
- Fecha: 2026-07-10

## Contexto

El proyecto necesita demostrar un pipeline de despliegue realista sin almacenar
credenciales permanentes y sin mantener la arquitectura activa en AWS.

Las alternativas consideradas fueron:

1. Access keys de un usuario IAM guardadas como secrets.
2. Un runner autoalojado con un perfil AWS local.
3. GitHub OIDC con credenciales STS temporales.
4. No ofrecer despliegue automatizado y limitarse a `cdk synth`.

## Decisión

Utilizar GitHub OIDC y un environment denominado `aws-ephemeral`.

El rol federado:

- solo confía en el repositorio y environment concretos;
- exige audiencia `sts.amazonaws.com`;
- solo delega en los roles del bootstrap de AWS CDK;
- no acepta access keys estáticas;
- limita la sesión del workflow a 30 minutos.

El pipeline se activa exclusivamente mediante `workflow_dispatch`, exige una
frase de confirmación, despliega el stack, ejecuta pruebas y llama a
`cdk destroy` con `if: always()`.

Se mantiene un segundo workflow de destrucción para incidentes de limpieza.

## Consecuencias positivas

- No existen secretos AWS de larga duración en GitHub.
- Las sesiones son temporales y trazables por `github.run_id`.
- La política de confianza está restringida por repositorio y environment.
- El despliegue no se activa mediante commits o pull requests.
- El ciclo de vida efímero reduce el riesgo de recursos olvidados.
- La CI valida que los guardrails OIDC continúan presentes.

## Consecuencias y riesgos

- Es necesario realizar el bootstrap de CDK una vez.
- El bootstrap y el rol OIDC son recursos persistentes de control.
- `if: always()` no garantiza limpieza ante la desaparición completa del runner.
- Un despliegue real puede generar cargos aunque sea breve.
- Los roles estándar de CDK deben revisarse antes de utilizar este patrón en una
  organización o cuenta de producción.

## Mitigaciones

- Workflow separado de destrucción de emergencia.
- Confirmación textual obligatoria.
- Environment de GitHub con aprobación manual opcional.
- Región y cuenta verificadas con `allowed-account-ids`.
- Tiempo máximo de job y sesión STS limitados.
- Artifact de evidencias con retención de siete días.
- Revisión manual de CloudFormation, servicios y Billing después de cada prueba.

## Evolución futura

En una organización AWS real se sustituiría el bootstrap por una configuración
centralizada, con cuentas separadas, SCP, permisos boundary, CloudTrail
organizativo y políticas de ejecución de CloudFormation específicas para el
portfolio de servicios permitido.
