# Validación AWS del shell GenAI cerrado — 17 de julio de 2026

### Alcance validado

- Despliegue efímero mediante GitHub Actions.
- Credenciales temporales mediante OIDC, con identidad y cuenta permitida
  verificadas.
- Synth y despliegue completados.
- Lambda GenAI dedicada con rol IAM independiente.
- Acciones IAM exactas de solo lectura y logging.
- Ruta JWT protegida por el scope `incidents.summarize`.
- Feature y provider desactivados.
- Respuesta autenticada cerrada HTTP 503.
- Respuesta anónima HTTP 401.
- Respuesta con scope incorrecto HTTP 403.
- Destroy y ausencia final verificados.
- Evidencia saneada generada.

### Resultado

- Resultado global: **SUCCESS**.
- Commit validado: `661f44e3c6dccbcfb819376404a533a5909a7970`.
- Región: `eu-west-1`.
- Timestamp del artefacto: `2026-07-17T13:45:57Z`.
- No se configuró ningún modelo, permiso o inferencia Amazon Bedrock.
- El cleanup quedó verificado; el stack, la Lambda GenAI y su log group estaban
  ausentes al terminar.

### IAM validado

- `dynamodb:GetItem`
- `logs:CreateLogStream`
- `logs:PutLogEvents`

### Limitaciones

Esta evidencia valida exclusivamente el patrón
**deployed + authorized + disabled + destroyed**. No valida inferencia real,
calidad semántica, groundedness mediante un modelo real, ni coste o latencia de
Amazon Bedrock. Tampoco selecciona o aprueba un modelo, habilita acciones
automáticas, demuestra production readiness o cambia ADR-013 a Accepted.

### Trazabilidad

El archivo `docs/evidence/genai-shell-aws-validation-2026-07-17.json` es una copia
validada byte a byte de `genai-shell-validation.json`, único archivo
contenido en el artefacto de GitHub Actions
`genai-shell-aws-validation-29584706366`, generado por el run `29584706366`.
Antes de la extracción, el ZIP del artefacto se verificó mediante el digest
`sha256:da0fd0507300f62f436c1fee97f7d075084b9531bd758302da1fdcb4d73a1ac0`.
Después, el JSON extraído superó `validate_evidence`, se comparó byte a byte y se
incorporó al repositorio sin modificaciones.

- [Evidencia JSON versionada](evidence/genai-shell-aws-validation-2026-07-17.json)
- [Workflow de despliegue efímero](../.github/workflows/deploy-ephemeral.yml)
- [Documentación de diseño](bedrock-incident-copilot.md)
- [ADR-013](adr/013-amazon-bedrock-incident-copilot.md)
