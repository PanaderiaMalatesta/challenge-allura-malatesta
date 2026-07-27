# Deploy en Oracle Cloud (OCI Compute)

Pendiente de ejecutar — pasos a seguir cuando la cuenta OCI Free Tier esté creada.

El bot usa long-polling hacia la API de Telegram, así que **no hace falta
abrir ningún puerto entrante** en la instancia — solo necesita salida a
internet (HTTPS), que viene habilitada por defecto.

1. Crear cuenta en [OCI Free Tier](https://www.oracle.com/cloud/free/) (requiere
   datos personales y verificación con tarjeta, sin cargo si te mantienes en
   el tier gratuito).
2. Crear una instancia Compute "Always Free":
   - Forma: `VM.Standard.E2.1.Micro` (AMD) o `VM.Standard.A1.Flex` (ARM, más
     recursos gratis).
   - Imagen: Ubuntu 22.04.
   - No es necesario modificar la Security List/NSG de la VCN (sin puertos
     entrantes que abrir).
3. Conectarse por SSH a la instancia y clonar el repo:
   ```bash
   sudo apt update && sudo apt install -y python3-pip python3-venv git
   git clone <url-del-repo>
   cd challenge-allura
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
4. Crear el archivo `.env` con `GOOGLE_API_KEY` y `TELEGRAM_BOT_TOKEN`, y
   construir el índice:
   ```bash
   python -m src.ingest
   ```
5. Dejar el bot corriendo de forma persistente. Opción simple con `nohup`:
   ```bash
   nohup python -m src.telegram_bot > bot.log 2>&1 &
   ```
   Opción más robusta (reinicia solo si el proceso o la VM se caen), crear
   `/etc/systemd/system/malatesta-bot.service`:
   ```ini
   [Unit]
   Description=Agente interno Malatesta - bot Telegram
   After=network.target

   [Service]
   WorkingDirectory=/home/ubuntu/challenge-allura
   ExecStart=/home/ubuntu/challenge-allura/.venv/bin/python -m src.telegram_bot
   Restart=always
   EnvironmentFile=/home/ubuntu/challenge-allura/.env

   [Install]
   WantedBy=multi-user.target
   ```
   y luego:
   ```bash
   sudo systemctl enable --now malatesta-bot
   ```
6. Confirmar que el bot responde escribiéndole desde Telegram.
7. Agregar al README una captura de la conversación con el bot como evidencia
   del deploy.
