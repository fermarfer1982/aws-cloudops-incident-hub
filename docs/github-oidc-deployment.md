# Despliegue efímero con GitHub OIDC

## Objetivo

El repositorio incluye un pipeline manual capaz de desplegar la arquitectura en
AWS, ejecutar pruebas de humo, conservar evidencias durante siete días y destruir
el stack en la misma ejecución.

La autenticación utiliza OpenID Connect (OIDC). GitHub solicita credenciales STS
temporales y no se guardan access keys de AWS en GitHub.

> El workflow no se ejecuta automáticamente. Mantenerlo sin configurar ni
> ejecutarlo conserva el laboratorio local a coste cero. Un despliegue real en
> AWS no puede prometer matemáticamente un cargo de 0,00; debe realizarse con
> créditos o Free Plan, alertas de facturación y revisión posterior de recursos.

## Modelo de confianza

```text
GitHub environment: aws-ephemeral
              │
              │ JWT OIDC de corta duración
              ▼
IAM role: cloudops-github-oidc-deploy
              │
              │ sts:AssumeRole
              ▼
Roles estándar del bootstrap de AWS CDK
              │
              ▼
CloudFormation despliega CloudOpsIncidentHubStack
```

La política de confianza exige simultáneamente:

- audiencia `sts.amazonaws.com`;
- repositorio `fermarfer1982/aws-cloudops-incident-hub`;
- environment de GitHub `aws-ephemeral`.

El `sub` admitido es exactamente:

```text
repo:fermarfer1982/aws-cloudops-incident-hub:environment:aws-ephemeral
```

El rol OIDC actúa como broker: no contiene permisos directos para crear toda la
arquitectura. Solo puede asumir los roles estándar del bootstrap de CDK en la
cuenta y región configuradas, leer la versión del bootstrap y consultar el estado
de CloudFormation.

## Archivos

| Archivo | Función |
|---|---|
| `.github/workflows/deploy-ephemeral.yml` | Desplegar, probar, recoger evidencias y destruir |
| `.github/workflows/destroy-ephemeral.yml` | Limpieza manual de emergencia |
| `bootstrap/github-oidc-role.yml` | Rol IAM y política de confianza restringida |
| `scripts/check_oidc_workflows.py` | Guardrails de seguridad validados por CI |

## Requisitos previos

Solo son necesarios para ejecutar el despliegue real:

1. Una cuenta AWS bajo control del propietario.
2. MFA habilitado para el usuario root.
3. Alertas de Free Tier y un presupuesto de gasto cero.
4. AWS CLI autenticada mediante IAM Identity Center o credenciales temporales.
5. Una región única, recomendada `eu-west-1`.
6. Un entorno CDK previamente inicializado.

No utilices access keys permanentes para GitHub Actions.

## 1. Crear el proveedor OIDC de GitHub

En AWS IAM:

```text
Identity providers
→ Add provider
→ OpenID Connect
```

Valores:

```text
Provider URL: https://token.actions.githubusercontent.com
Audience:     sts.amazonaws.com
```

Solo debe existir un proveedor con esa URL por cuenta AWS. Conserva su ARN:

```text
arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com
```

## 2. Bootstrap de AWS CDK

Este paso se realiza una sola vez desde una sesión administrativa temporal:

```bash
cd infrastructure
cdk bootstrap aws://ACCOUNT_ID/eu-west-1
```

El bootstrap crea el stack `CDKToolkit`, con bucket de assets y roles de
despliegue. Revisa la plantilla y las políticas del bootstrap antes de utilizarlo
en una cuenta compartida.

No elimines `CDKToolkit` si la cuenta tiene otros proyectos CDK. Para una cuenta
de laboratorio dedicada, revisa y vacía sus assets cuando finalice la práctica.

## 3. Crear el rol OIDC del repositorio

Desde la raíz del repositorio:

```bash
aws cloudformation deploy \
  --template-file bootstrap/github-oidc-role.yml \
  --stack-name cloudops-github-oidc \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    GitHubOidcProviderArn=arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com \
    DeploymentRegion=eu-west-1
```

Obtén el ARN del rol:

```bash
aws cloudformation describe-stacks \
  --stack-name cloudops-github-oidc \
  --query "Stacks[0].Outputs[?OutputKey=='RoleArn'].OutputValue" \
  --output text
```

## 4. Configurar el environment de GitHub

En GitHub:

```text
Settings
→ Environments
→ New environment
→ aws-ephemeral
```

Configura estas variables del environment:

| Variable | Ejemplo |
|---|---|
| `AWS_REGION` | `eu-west-1` |
| `AWS_ACCOUNT_ID` | `123456789012` |
| `AWS_DEPLOY_ROLE_ARN` | `arn:aws:iam::123456789012:role/cloudops-github-oidc-deploy` |

No se necesitan secrets de tipo `AWS_ACCESS_KEY_ID` o
`AWS_SECRET_ACCESS_KEY`.

Como control adicional, el environment puede requerir aprobación manual antes de
ejecutar el job.

## 5. Ejecutar el despliegue efímero

Desde GitHub:

```text
Actions
→ Deploy ephemeral AWS lab
→ Run workflow
```

Selecciona `main` y escribe exactamente:

```text
DEPLOY-AND-DESTROY
```

El job realiza:

1. Validación de confirmación y variables.
2. Intercambio OIDC por credenciales STS de 30 minutos.
3. Tests de infraestructura, `cdk synth` y guardrails de coste.
4. `cdk deploy` del stack.
5. Prueba de `/health`.
6. Publicación de una incidencia de prueba.
7. Confirmación de procesamiento asíncrono EventBridge → SQS → Lambda.
8. Subida de evidencias como artifact durante siete días.
9. `cdk destroy --force`, incluso si una prueba anterior falla.
10. Confirmación de que CloudFormation ya no encuentra el stack.

## 6. Limpieza de emergencia

Si una ejecución se cancela desde fuera del job o el runner desaparece antes de
la fase de limpieza:

```text
Actions
→ Destroy ephemeral AWS lab
→ Run workflow
```

Escribe:

```text
DESTROY-EPHEMERAL-STACK
```

Después revisa manualmente en AWS:

- CloudFormation: el stack `CloudOpsIncidentHubStack` no existe.
- Lambda: no quedan funciones con el prefijo del stack.
- SQS: no quedan las colas `cloudops-incident-*`.
- EventBridge: no queda el bus `cloudops-incident-hub`.
- DynamoDB: no queda la tabla del stack.
- CloudWatch: no quedan dashboard ni alarmas del proyecto.
- Billing: no aparecen recursos inesperados.

## Límites de la automatización

`if: always()` mejora la probabilidad de ejecutar la limpieza, pero no sustituye
un control externo. Un runner puede apagarse, perder conectividad o ser cancelado
antes de llegar al paso de destrucción. Por eso existe un workflow separado de
emergencia y una revisión manual obligatoria.

El pipeline no se dispara con `push`, `pull_request` ni `pull_request_target`.
Solo acepta `workflow_dispatch` desde la rama `main` y usa una confirmación
explícita para reducir ejecuciones accidentales.
