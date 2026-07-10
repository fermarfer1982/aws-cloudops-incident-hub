# Checklist de activación OIDC

Esta lista solo es necesaria para realizar una demostración real en AWS. El
repositorio, Docker local y GitHub Pages funcionan sin completarla.

- [ ] MFA habilitado en la cuenta AWS.
- [ ] Alertas de Free Tier habilitadas.
- [ ] Presupuesto de gasto cero configurado.
- [ ] Región única elegida (`eu-west-1`).
- [ ] Proveedor OIDC `token.actions.githubusercontent.com` creado en IAM.
- [ ] Entorno AWS CDK inicializado con `cdk bootstrap`.
- [ ] Stack `cloudops-github-oidc` creado desde la plantilla del repositorio.
- [ ] Environment de GitHub `aws-ephemeral` creado.
- [ ] Variable `AWS_REGION` configurada en el environment.
- [ ] Variable `AWS_ACCOUNT_ID` configurada en el environment.
- [ ] Variable `AWS_DEPLOY_ROLE_ARN` configurada en el environment.
- [ ] No existen secrets `AWS_ACCESS_KEY_ID` ni `AWS_SECRET_ACCESS_KEY`.
- [ ] Workflow ejecutado desde `main` con `DEPLOY-AND-DESTROY`.
- [ ] Artifact de evidencias descargado o revisado.
- [ ] Paso `Destroy ephemeral stack` finalizado correctamente.
- [ ] CloudFormation confirma que el stack de aplicación no existe.
- [ ] Revisión manual de Lambda, SQS, DynamoDB, EventBridge y CloudWatch.
- [ ] Billing revisado después de la práctica.
