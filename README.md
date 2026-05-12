# Telegram Forwarder hacia n8n

Este proyecto escucha mensajes nuevos de un chat concreto de Telegram usando Telethon con una cuenta real de Telegram, y envía cada mensaje como JSON a un webhook de n8n.

No usa un bot para leer el chat origen. Telethon inicia sesión como cliente de una cuenta normal de Telegram.

## Archivos

- `app.py`: servicio principal.
- `web.py`: panel web de gestion.
- `list_chats.py`: lista tus chats para encontrar `SOURCE_CHAT`.
- `requirements.txt`: dependencias Python.
- `.env.example`: plantilla de configuración sin secretos.
- `Dockerfile`: imagen del servicio.
- `docker-compose.yml`: interfaz web y forwarder con reinicio automático.
- `data/`: carpeta persistente para la sesión de Telethon cuando se usa Docker.
- `umbrel-app-store.yml` y `mason-telegram-forwarder/`: tienda comunitaria de Umbrel lista para anadir desde Umbrel.

## Conseguir TELEGRAM_API_ID y TELEGRAM_API_HASH

1. Entra en https://my.telegram.org.
2. Inicia sesión con tu cuenta de Telegram.
3. Ve a `API development tools`.
4. Crea una aplicación.
5. Copia `api_id` y `api_hash`.

Guarda esos valores solo en `.env`. No los pegues en el código ni los subas a Git.

## Configurar .env

Copia la plantilla:

```bash
cp .env.example .env
```

Edita `.env`:

```env
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
SOURCE_CHAT=-1001234567890
N8N_WEBHOOK_URL=https://mi-dominio.com/webhook/telegram-forward
SESSION_NAME=/data/telegram_forwarder_session
```

`SOURCE_CHAT` puede ser:

- un ID numérico, por ejemplo `-1001234567890`
- varios IDs separados por coma, por ejemplo `-1001234567890,-1009876543210`
- un username, por ejemplo `mi_canal`
- un enlace tipo `https://t.me/mi_canal`

Si cada valor parece número, el script lo convierte a `int`. Para varios chats se recomienda usar IDs numéricos.

## Panel web

Con Docker Compose puedes levantar la interfaz:

```bash
docker compose up -d --build
```

Abre:

```text
http://localhost:8080
```

Desde el panel puedes:

- guardar `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `SOURCE_CHAT` y `N8N_WEBHOOK_URL`
- pedir el código de Telegram
- completar login con código y 2FA
- listar chats
- probar el webhook de n8n

El forwarder lee la configuración desde:

```text
./data/config.env
```

Si cambias `SOURCE_CHAT` o `N8N_WEBHOOK_URL`, reinicia el servicio para aplicar la nueva configuración:

```bash
docker compose restart forwarder
```

## Primer login con Telegram

La primera ejecución tiene que ser interactiva para crear el archivo de sesión.

Con Docker Compose:

```bash
docker compose up -d --build
```

Despues entra en `http://localhost:8080` y usa la seccion `Login Telegram`.

También puedes hacerlo sin Docker:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Pasos del login:

1. Crea `.env` desde `.env.example`.
2. Rellena `TELEGRAM_API_ID` y `TELEGRAM_API_HASH`.
3. Ejecuta `python app.py` manualmente la primera vez.
4. Introduce el teléfono con prefijo internacional, por ejemplo `+34XXXXXXXXX`.
5. Introduce el código que llega a Telegram.
6. Introduce la contraseña 2FA si la cuenta la tiene.
7. Verifica que se crea el archivo de sesión.
8. Para el script con `Ctrl+C`.
9. Déjalo arrancando como servicio con Docker Compose.

Con la configuración de Docker, la sesión queda en:

```text
./data/telegram_forwarder_session.session
```

Ese archivo permite volver a arrancar sin pedir código cada vez.

## Listar chats

Después del primer login, ejecuta:

```bash
docker compose run --rm web python list_chats.py
```

O sin Docker:

```bash
python list_chats.py
```

Verás algo así:

```text
Nombre del chat => -1001234567890
```

Copia el ID correcto en `SOURCE_CHAT`.

## Configurar n8n

1. Crea un workflow nuevo en n8n.
2. Añade un nodo `Webhook`.
3. Método: `POST`.
4. Path: `telegram-forward`.
5. Prueba primero con la Test URL.
6. Cuando funcione, copia la Production URL.
7. Pon la Production URL en `N8N_WEBHOOK_URL`.
8. Activa el workflow.

Importante: si usas la Production URL, el workflow debe estar activo. La Test URL solo funciona mientras n8n está escuchando la prueba.

El JSON recibido tendrá esta forma:

```json
{
  "chat_id": -1001234567890,
  "message_id": 123,
  "sender_id": 987654321,
  "text": "Mensaje recibido",
  "date": "2026-05-12T12:34:56+00:00",
  "has_media": false,
  "grouped_id": null
}
```

Desde n8n puedes reenviar ese contenido a WhatsApp usando el proveedor que prefieras, por ejemplo WhatsApp Cloud API, Twilio, Evolution API, Waha u otro gateway compatible.

## Levantar como servicio

Cuando ya existe la sesión y `SOURCE_CHAT` está configurado:

```bash
docker compose up -d --build
```

El servicio tiene:

```yaml
restart: unless-stopped
```

Eso hace que se reinicie si falla y que vuelva a arrancar tras reiniciar el servidor, siempre que Docker arranque con el sistema.

## Ver logs

```bash
docker compose logs -f forwarder
```

Logs de la interfaz:

```bash
docker compose logs -f web
```

## Reiniciar

```bash
docker compose restart forwarder
docker compose restart web
```

## Umbrel Community App Store

El repositorio esta preparado como Community App Store de Umbrel:

```text
umbrel-app-store.yml
mason-telegram-forwarder/
  umbrel-app.yml
  docker-compose.yml
  exports.sh
  icon.svg
```

Para instalarla como tienda comunitaria:

1. Espera a que GitHub Actions publique `ghcr.io/blulyk/telegram-forwarder:0.1.8`.
2. En Umbrel, ve a App Store y anade `https://github.com/Blulyk/mason-telegram-forwarder` como Community App Store.
3. Instala `Telegram Forwarder` desde la tienda comunitaria.

Si Umbrel no muestra la actualizacion, fuerza el refresco por SSH:

```bash
cd ~/umbrel
sudo scripts/repo update
sudo scripts/app update mason-telegram-forwarder
```

En versiones antiguas puede ser:

```bash
sudo ~/umbrel/scripts/repo update
sudo ~/umbrel/scripts/app update mason-telegram-forwarder
```

## Parar

```bash
docker compose down
```

No borres `./data` si quieres conservar la sesión.

## Actualizar

Para actualizar dependencias o código:

```bash
docker compose up -d --build
```

No uses comandos que borren volúmenes o la carpeta `data`, porque perderías la sesión y tendrías que iniciar sesión otra vez.

## Seguridad

- No compartas `.env`.
- No compartas `*.session`.
- No subas `data/` a Git.
- El archivo `.session` equivale a una sesión iniciada de Telegram.
- Si sospechas que la sesión se ha expuesto, cierra sesiones desde Telegram y crea una nueva.
- No pegues `TELEGRAM_API_HASH` en chats, issues ni logs.

## Criterios de funcionamiento

- `python app.py` permite iniciar sesión con tu cuenta real de Telegram.
- `python list_chats.py` lista IDs de chats.
- `SOURCE_CHAT` limita la escucha a un solo chat.
- Cada mensaje nuevo genera un POST al webhook de n8n.
- Si n8n devuelve error, queda registrado en logs y el proceso sigue vivo.
- Docker Compose reinicia el servicio si falla.
- El archivo `.session` queda persistido en `./data`.
