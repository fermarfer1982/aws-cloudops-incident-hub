# Seguridad

## MVP

- Validación de entradas mediante Pydantic.
- Longitudes máximas y formato estricto del tipo de evento.
- IAM de Lambda limitado a la tabla DynamoDB del stack.
- Sin access keys en el repositorio.
- Variables de entorno únicamente para configuración no secreta.
- CORS abierto solo para facilitar el laboratorio; en producción se restringiría al dominio del frontend.
- La API pública de producción incorporaría autenticación con Cognito o un authorizer JWT.

## Pipeline futuro

El despliegue desde GitHub utilizará OIDC para obtener credenciales temporales, sin secretos AWS de larga duración almacenados en GitHub.
