# Deploy en Railway

Se evaluó Oracle Cloud (OCI Compute Always Free) primero, pero la verificación
de cuenta demora hasta 24 horas — Railway permite desplegar en minutos con
login por GitHub, así que se usó para esta entrega. El enunciado del challenge
permite cualquier plataforma, OCI era solo una sugerencia.

El bot usa long-polling hacia la API de Telegram, así que no hace falta
exponer ningún puerto ni configurar networking.

## Pasos (ya ejecutados para este proyecto)

1. Crear cuenta en [railway.app](https://railway.app) con "Continue with GitHub".
2. Aceptar los términos (Privacy and Data Policy + Fair Use Policy).
3. Instalar la Railway GitHub App, con acceso limitado **solo** al repo
   `challenge-allura-malatesta` (Settings → Only select repositories).
4. New Project → GitHub Repository → seleccionar el repo. Railway detecta
   Python automáticamente (Nixpacks).
5. En la pestaña **Variables** del servicio, cargar (Raw Editor):
   ```
   COHERE_API_KEY=...
   TELEGRAM_BOT_TOKEN=...
   ```
6. En **Settings → Deploy → Custom Start Command**, poner:
   ```
   python -m src.ingest && python -m src.telegram_bot
   ```
   (reconstruye el índice FAISS en cada deploy antes de levantar el bot,
   porque `data/index_recetas/` está en `.gitignore` y no se sube al repo).
7. Deploy. Verificar en **Deployments → Deploy Logs** que aparezcan líneas
   `INFO:httpx:HTTP Request: POST https://api.telegram.org/bot.../sendMessage
   "HTTP/1.1 200 OK"` sin errores.

## Costo
Railway da un trial de $5 USD o 30 días (lo que se cumpla primero) sin tarjeta
para arrancar. Un bot de bajo tráfico como este consume centavos por día de
ese crédito.
