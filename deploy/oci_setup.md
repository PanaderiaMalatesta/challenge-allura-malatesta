# Deploy en Oracle Cloud (OCI Compute)

Pendiente de ejecutar — pasos a seguir cuando la cuenta OCI Free Tier esté creada.

1. Crear cuenta en [OCI Free Tier](https://www.oracle.com/cloud/free/) (requiere
   datos personales y verificación con tarjeta, sin cargo si te mantienes en
   el tier gratuito).
2. Crear una instancia Compute "Always Free":
   - Forma: `VM.Standard.E2.1.Micro` (AMD) o `VM.Standard.A1.Flex` (ARM, más
     recursos gratis).
   - Imagen: Ubuntu 22.04.
   - Abrir el puerto 8000 en la lista de seguridad (Security List / Network
     Security Group) de la VCN, regla de ingreso TCP 0.0.0.0/0:8000.
3. Conectarse por SSH a la instancia y clonar el repo:
   ```bash
   sudo apt update && sudo apt install -y python3-pip python3-venv git
   git clone <url-del-repo>
   cd challenge-allura
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
4. Crear el archivo `.env` con `GOOGLE_API_KEY` y construir el índice:
   ```bash
   python -m src.ingest
   ```
5. Levantar el servidor (dejarlo corriendo con `systemd` o `nohup`):
   ```bash
   nohup uvicorn src.server:app --host 0.0.0.0 --port 8000 &
   ```
6. Confirmar acceso público en `http://<ip-publica-instancia>:8000`.
7. Agregar la IP/captura al README como evidencia del deploy.
