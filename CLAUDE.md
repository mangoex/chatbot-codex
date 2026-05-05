# CLAUDE.md - WhatsApp Bot Template

Este repositorio es una plantilla publica para crear y desplegar bots de WhatsApp en Easypanel.
Ayuda al usuario a personalizar el prompt, validar variables de entorno y desplegar sin filtrar
secretos.

## Flujo recomendado

1. Validar `.env`.
   - Requeridos para deploy: `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`,
     `WHATSAPP_VERIFY_TOKEN`, `PUBLIC_BASE_URL`, `OPENAI_API_KEY`, `DATABASE_URL`,
     `ADMIN_USER`, `ADMIN_PASSWORD`, `SESSION_SECRET`.
   - `DATABASE_URL` y `RELOAD_TOKEN` pueden generarse durante el deploy.
   - `META_APP_SECRET` es opcional.

2. Validar `prompts/system.md`.
   - Si conserva placeholders como `[NOMBRE DEL NEGOCIO]`, avisar que debe personalizarse.
   - No hardcodear datos privados en el prompt si el repo sera publico.

3. Usar el skill `whatsapp-bot-deployer`.
   - Crear repositorio privado en GitHub.
   - Provisionar Postgres en Easypanel.
   - Crear app publica con dominio `PUBLIC_BASE_URL`.
   - Configurar env vars.
   - Desplegar y verificar `/health` y handshake `/webhooks/whatsapp`.
   - Generar `META_SETUP.md` local, ignorado por git.

## Reglas de seguridad

- Nunca commitear `.env`, `.mcp.json`, `META_SETUP.md` ni `execution/`.
- Antes de `git add`, revisar `git status`.
- Antes de `git commit` o `git push`, buscar secretos:

```bash
rg -n "api[_-]?key|secret|token|password|bearer|ghp_|sk-|EAA" .
```

- Si aparece un valor real, detenerse y pedir rotacion de credenciales.
- No usar `git add -A` a ciegas.

## Cambios de funcionalidad

Mantener el template generico. No agregar integraciones de agenda, correo, filtros de prueba
o CRMs externos salvo que el usuario pida crear una variante privada.
